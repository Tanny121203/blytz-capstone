Blytz garment assets (original artwork, no third-party content)

FILES
  <garment>-<view>.svg    tee, polo, hoodie, jersey  x  front, back   (800x800 viewBox)
  garments.json           garments, their SVG files, and print areas (SVG units)
  tools/generate_garments.py   optional: regenerates the SVGs into tools/output/

WHERE TO PUT THEM IN THE DJANGO PROJECT
  static/garments/*.svg
  static/garments/garments.json
  tools/generate_garments.py   (optional)

SVG LAYERS (ids are prefixed, e.g. "tee-front-")
  ground    soft floor shadow
  base      garment silhouette, filled with CSS variable --garment
  art       empty slot for artwork (clipped to the garment)   [not used by the editor]
  details   collar, cuffs, seams, buttons, pocket, drawstrings (uses --trim, --string)
  shade     folds, highlights, grain and weave on top

COLORS  set --garment (and --trim for the jersey, --string for hoodie drawstrings) on a parent element.
Inline the SVG text in the page (an <img> cannot see page CSS variables).
