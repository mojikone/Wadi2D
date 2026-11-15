Pre-release for testing; a fix release over 0.3.0, found by installing 0.3.0 on a PC with no usable NVIDIA card.

- **The installer chooses the engine from the NVIDIA driver.** It finds `nvidia-smi` where the driver installs it (not only on the PATH), or reads Windows' list of display adapters, and installs the GPU engine only with a driver of 527.41 or later and a card of compute capability 5.0 or later. An old card or driver gets the CPU engine with one line saying why, instead of a 2 GB CUDA download and a warning.
- **Preview rain says the area reduction once:** "Depths with no area reduction, on the hydrology step of 5 min." in place of a sentence that contradicted itself.

Install: unzip `Wadi2D-0.3.1-windows.zip`, close QGIS, double-click `install_wadi2d.bat`. Everything else as in 0.3.0.
