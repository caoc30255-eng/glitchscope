#include "stm32f10x.h"
#include "image_stream.h"

#define BAUD 1000000u
#define TX_WATCHDOG_US 10000u
/* Visible in Keil Watch; all values are runtime RCC-derived, not measured Hz. */
img_stream_t dut;
img_ring_t rx_ring;
volatile uint32_t timer_upper, rx_last_us, rx_irq_bytes, rx_irq_errors;
volatile uint32_t dut_pclk2_hz, dut_tim2_hz, dut_brr, dut_clock_fault;
volatile uint32_t max_service_gap_us;
volatile uint32_t rx_capture_observations;
volatile uint32_t rx_capture_last_observed_us, rx_capture_last_flags;

/* GPIO PA10 independently feeds EXTI10's falling-edge pending latch. IMR/EMR
 * stay masked: no interrupt for every data edge, no alternate-function timer
 * sharing. PR stays set even if the pin returns high between main services.
 * W1C only line10. Coalesced edges before the clear are conservatively covered
 * by the subsequent observation timestamp; never classify this take as quiet. */
static uint8_t capture_take(void)
{
    uint32_t flags = EXTI->PR & (1u << 10);
    if (flags == 0u) return 0u;
    EXTI->PR = (1u << 10);
    rx_capture_last_flags = flags;
    rx_capture_observations++;
    return 1u;
}

void TIM2_IRQHandler(void)
{
    if ((TIM2->SR & TIM_SR_UIF) != 0u) {
        timer_upper += 65536u;
        TIM2->SR = (uint16_t)~TIM_SR_UIF;
    }
}
static uint32_t micros(void)
{
    uint32_t mask = __get_PRIMASK(), hi, lo;
    __disable_irq();
    hi = timer_upper;
    lo = TIM2->CNT;
    if ((TIM2->SR & TIM_SR_UIF) != 0u) {
        /* Pending wrap: re-read CNT after detecting UIF. Interrupt will account
         * for this wrap later. Do not clear UIF here. */
        hi += 65536u;
        lo = TIM2->CNT;
    }
    __set_PRIMASK(mask);
    return hi + lo;
}
static uint32_t apb_div(uint32_t field)
{
    return field < 4u ? 1u : (1u << (field - 3u));
}
static uint8_t clock_and_timer_init(void)
{
    uint32_t cfgr, pclk1, apb1_div, apb2_div;
    SystemCoreClockUpdate();
    cfgr = RCC->CFGR;
    apb1_div = apb_div((cfgr >> 8) & 7u);
    pclk1 = SystemCoreClock / apb1_div;
    apb2_div = apb_div((cfgr >> 11) & 7u);
    dut_pclk2_hz = SystemCoreClock / apb2_div;
    dut_tim2_hz = apb1_div == 1u ? pclk1 : pclk1 * 2u;
    dut_brr = (dut_pclk2_hz + BAUD / 2u) / BAUD;
    /* Require exact 1 us prescale and exact 1 Mbps integer divisor initially.
     * HSE failure/fallback that cannot supply >=16 MHz must fail closed. */
    if (dut_tim2_hz < 1000000u || dut_tim2_hz % 1000000u != 0u ||
        dut_brr < 16u || dut_brr > 65535u || dut_pclk2_hz % BAUD != 0u)
        return 0u;
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    RCC->APB1RSTR |= RCC_APB1RSTR_TIM2RST;
    RCC->APB1RSTR &= ~RCC_APB1RSTR_TIM2RST;
    TIM2->PSC = dut_tim2_hz / 1000000u - 1u;
    TIM2->ARR = 65535u;
    TIM2->EGR = TIM_EGR_UG;
    TIM2->SR = 0u;
    timer_upper = 0u;
    TIM2->DIER = TIM_DIER_UIE;
    NVIC_SetPriority(TIM2_IRQn, 0u);
    NVIC_EnableIRQ(TIM2_IRQn);
    TIM2->CR1 = TIM_CR1_CEN;
    return 1u;
}
static void uart_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_AFIOEN | RCC_APB2ENR_USART1EN;
    /* Default USART1 routing only. PA9 AF push-pull; PA10 floating input.
     * No external wiring/power assumption is implemented by this firmware. */
    AFIO->MAPR &= ~AFIO_MAPR_USART1_REMAP;
    GPIOA->CRH = (GPIOA->CRH & ~((15u << 4) | (15u << 8))) |
                  (11u << 4) | (4u << 8);
    /* EXTI10 source GPIOA; line10 is exclusively reserved by this firmware.
     * Mask CPU/event outputs but leave the falling detector enabled. */
    EXTI->IMR &= ~(1u << 10);
    EXTI->EMR &= ~(1u << 10);
    AFIO->EXTICR[2] &= ~(15u << 8);
    EXTI->RTSR &= ~(1u << 10);
    EXTI->FTSR |= (1u << 10);
    EXTI->PR = (1u << 10);
    USART1->CR1 = 0u;
    USART1->CR2 = 0u;
    USART1->CR3 = USART_CR3_EIE;
    USART1->BRR = dut_brr;
    USART1->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE |
                  USART_CR1_RXNEIE | USART_CR1_PEIE;
    NVIC_SetPriority(USART1_IRQn, 1u);
    NVIC_EnableIRQ(USART1_IRQn);
}
void USART1_IRQHandler(void)
{
    uint32_t sr = USART1->SR;
    img_event_t e;
    if ((sr & (USART_SR_RXNE | USART_SR_PE | USART_SR_FE |
               USART_SR_NE | USART_SR_ORE)) == 0u) return;
    /* RM0008: capture SR, then read DR exactly once. Keep error-only event. */
    e.data = (uint8_t)USART1->DR;
    e.flags = (uint8_t)(sr & 15u);
    e.has_byte = (uint8_t)((sr & USART_SR_RXNE) != 0u);
    e.reserved = 0u;
    /* Account for pre-completion data-bit edges BEFORE anchoring this event's
     * idle timer. Edges after W1C remain sticky. If a later byte/error
     * consumes a latch before main sees it, its queued event blocks closure. */
    if (capture_take()) rx_capture_last_observed_us = micros();
    e.us = micros();
    rx_last_us = e.us;
    if (e.has_byte) rx_irq_bytes++;
    if (e.flags) rx_irq_errors++;
    (void)img_ring_push(&rx_ring, e);
}
int main(void)
{
    uint32_t overflow_seen = 0u, tx_start = 0u, now, mask, previous;
    uint16_t tx_pos = 0u;
    uint8_t tx_active = 0u, popped, quiet, activity;
    img_event_t e;
    if (!clock_and_timer_init()) {
        dut_clock_fault = 1u;
        for (;;) { /* USART stays disabled. */ }
    }
    img_stream_init(&dut, micros());
    uart_init();
    previous = micros();
    for (;;) {
        now = micros();
        if (now - previous > max_service_gap_us) max_service_gap_us = now - previous;
        previous = now;
        /* Ring pop/reset and quiet snapshot are short atomic sections.
         * Parsing / CRC / TX never hold interrupts disabled. */
        mask = __get_PRIMASK();
        __disable_irq();
        activity = 0u;
        if (overflow_seen != rx_ring.overflow) {
            overflow_seen = rx_ring.overflow;
            rx_ring.tail = rx_ring.head;
            e.us = rx_last_us;
            popped = 2u;
            quiet = 0u;
        } else {
            popped = img_ring_pop(&rx_ring, &e);
            /* Do not apply an observation at 'now' before older queued events. */
            if (!popped) activity = capture_take();
            now = micros();
            if (activity) rx_capture_last_observed_us = now;
            quiet = (uint8_t)(!popped && !activity &&
                    (EXTI->PR & (1u << 10)) == 0u &&
                    (GPIOA->IDR & (1u << 10)) != 0u &&
                    (USART1->SR & (USART_SR_RXNE | 15u)) == 0u);
        }
        __set_PRIMASK(mask);
        if (popped == 2u) img_stream_overflow(&dut, e.us);
        else if (popped) img_stream_feed(&dut, e);
        else {
            if (activity) img_stream_rx_activity(&dut, now);
            img_stream_poll(&dut, now, quiet);
        }
        if (dut.state == IS_TX) {
            if (!tx_active) {
                /* CRC/encoding can take time. Recheck immediately before FIRST
                 * DR write. No interrupts/edge clears between check and write.
                 * Conservative suppression is preferable to premature OK. */
                mask = __get_PRIMASK();
                __disable_irq();
                if (rx_ring.head != rx_ring.tail || rx_ring.overflow != overflow_seen ||
                    (EXTI->PR & (1u << 10)) != 0u ||
                    (GPIOA->IDR & (1u << 10)) == 0u ||
                    (USART1->SR & (USART_SR_RXNE | 15u)) != 0u) {
                    img_stream_tx_inhibited(&dut, micros());
                } else if ((USART1->SR & USART_SR_TXE) != 0u) {
                    tx_active = 1u; tx_pos = 0u; tx_start = micros();
                    USART1->DR = dut.tx[tx_pos++];
                }
                __set_PRIMASK(mask);
                if (!tx_active) continue;
            }
            if (micros() - tx_start >= TX_WATCHDOG_US) {
                /* Do not claim TC: disable transmitter, latch diagnostic. Reset
                 * / operator intervention required; no retry by this firmware. */
                USART1->CR1 &= ~USART_CR1_TE;
                img_stream_tx_failed(&dut, micros());
                for (;;) { }
            }
            if (tx_pos < dut.tx_len && (USART1->SR & USART_SR_TXE) != 0u)
                USART1->DR = dut.tx[tx_pos++];
            if (tx_pos == dut.tx_len && (USART1->SR & USART_SR_TC) != 0u) {
                img_stream_tx_complete(&dut, micros());
                tx_active = 0u;
            }
        }
    }
}
