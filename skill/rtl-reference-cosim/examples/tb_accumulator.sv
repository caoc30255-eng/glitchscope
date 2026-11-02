`timescale 1ns/1ps
module tb_accumulator;
 logic clk=0,rst=1,in_valid=0,out_ready=1;logic [7:0] din=0;wire in_ready,valid;wire [7:0] data;
 accumulator dut(.*);
 integer f,c,k;reg [7:0] ea,ed;reg ev,accepting,er;
 initial begin
  f=$fopen("actual.csv","w");if(f==0)$fatal(1,"SKILL_RTL_FAIL file open");
  $fwrite(f,"case,cycle,ready,valid,data,acc\n");
  for(c=0;c<6;c=c+1)begin
   ea=0;ed=0;ev=0;
   for(k=0;k<64;k=k+1)begin
    clk=0;rst=(k<2)||((c==2)&&((k==16)||(k==32)))||((c==5)&&(k==20));
    in_valid=((k+c)%3!=0);out_ready=1;din=(k*7+c*11)&255;
    if(c==1)begin in_valid=1;din=250;end
    if(c==3)out_ready=((k%5)!=0)&&((k%5)!=1);
    if((c==4)||(c==5))begin out_ready=!((k>=10)&&(k<30));in_valid=1;end
    accepting=!ev||out_ready;
    if(rst)begin ea=0;ed=0;ev=0;end
    else if(accepting)begin ev=in_valid;if(in_valid)begin ea=ea+din;ed=ea;end end
    er=!ev||out_ready;
    #5;clk=1;#1;
    $fwrite(f,"%0d,%0d,%0d,%0d,%0d,%0d\n",c,k,in_ready,valid,data,dut.acc);
    if(in_ready!==er || valid!==ev || data!==ed || dut.acc!==ea)$fatal(1,"SKILL_RTL_FAIL case=%0d cycle=%0d",c,k);
    #4;
   end
  end
  $fclose(f);$display("SKILL_RTL_PASS cases=6 cycles=384");$finish;
 end
endmodule
