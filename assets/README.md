# Assets Directory

This directory contains assets for the TLS Certificate Monitor application.

## Files

- `icon.ico` - Windows application icon (placeholder - add your own 32x32 or 48x48 ICO file)

## Creating an Icon

To create a proper Windows icon:

1. Create a 32x32 or 48x48 pixel image
2. Convert to ICO format using online tools or ImageMagick:
   ```bash
   convert icon.png -resize 32x32 icon.ico
   ```
3. Replace the placeholder icon.ico file

For now, the build will skip the icon if the file doesn't exist.