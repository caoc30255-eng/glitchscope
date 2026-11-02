# Third-party notices

The root MIT license applies only to project-owned contributions. It does not relicense vendor IP, device packs, models derived under their own data terms, fonts or copied third-party headers.

|Component|Where / license|
|---|---|
|emlearn|src/ps/workbench/vendor/edge/oss/third_party; original MIT license retained|
|scikit-learn|same tree; original BSD and bundled dependency license texts retained|
|scikit-activeml, makefun|same tree; original package license texts retained|
|Inter, JetBrains Mono, Noto fonts|src/ps/workbench/web/fonts; original OFL texts retained|
|STM32 startup/system code|src/stm32/keil/rte; original Arm/Keil/ST copyright headers retained; see src/stm32/licenses|
|Vivado block design/IP/generated wrapper|Requires independently licensed AMD tools; vendor IP is not granted under this project's MIT license|
|PYNQ, NumPy, Pillow, browser and compiler runtimes|External dependencies, not vendored installers; obey upstream terms|

Do not redistribute Keil device packs, Vivado installations or board vendor documentation disks as part of this repository. Download them from their owners. Historical portrait/dinosaur input images and screenshots have not received an explicit public-media rights clearance in this delivery and are excluded from the public source tree. Original review evidence belongs in the separate assessment package, not in a public Git push.

If an upstream file contains more restrictive terms than this summary, its original terms take precedence. Build artifacts retain their originating license obligations; binary inclusion is not a transfer of third-party ownership.

Enclosure HTML viewers embed Three.js, STLLoader and OrbitControls under MIT. Copyright and license are retained in hardware/enclosure/third_party_notices.md.
