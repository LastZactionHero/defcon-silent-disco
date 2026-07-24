# Aggregator for USER_C_MODULES. Point the build at THIS file:
#   make -C ports/rp2 BOARD=RPI_PICO USER_C_MODULES=<firmware>/cmodules/micropython.cmake
# Add future native modules by include()-ing their micropython.cmake here.

include(${CMAKE_CURRENT_LIST_DIR}/mp3/micropython.cmake)
