"""Title and legend round the pixel-method renders."""

from s05b_frame import depth_legend, frame, hazard_legend

frame("render_pixel_depth.png", "Wadi2D rain-on-grid, full project extent: maximum depth at the 5 m pixel", "Wadi2D_full_extent_PIXEL_DEPTH.jpg", depth_legend)
frame("render_pixel_hazard.png", "Wadi2D rain-on-grid, full project extent: AIDR hazard H1 to H6 at the 5 m pixel", "Wadi2D_full_extent_PIXEL_HAZARD_H1-H6.jpg", hazard_legend)
