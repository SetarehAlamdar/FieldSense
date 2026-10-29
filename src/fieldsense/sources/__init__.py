"""Data sources. Each module talks to one service and caches what it downloads.

Heavy optional libraries (rasterio for HLS) are only imported when you import that module,
so `import fieldsense` stays fast and works without them.
"""
