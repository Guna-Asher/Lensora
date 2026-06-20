# Screen Detection Test Fixtures

Place real test images here to measure detection accuracy against actual photographs.

## Directory Structure

```
fixtures/
├── laptop_thin_bezel/    # Modern laptop photos (MacBook, XPS, etc.)
├── monitor_dark_desk/    # Black monitor on dark desk
├── phone_notch/          # iPhone or Android with notch
├── phone_punch_hole/     # Android with punch-hole camera
├── tablet/               # iPad or Android tablet
├── angled_30/            # Photos taken ~30° off-axis
├── angled_45/            # Photos taken ~45° off-axis
├── angled_60/            # Photos taken ~60° off-axis (boundary case)
├── glare/                # Screens with visible reflections
├── dark_mode/            # Dark mode screen content
├── light_mode/           # Light mode screen content
├── multi_monitor/        # Setups with 2+ monitors
├── busy_background/      # Cluttered desk/environment
└── partial/              # Screen partially out of frame
```

## Supported Formats
- `.jpg` / `.jpeg`
- `.png`
- `.webp`

## Running Tests Against Fixtures

```bash
cd /app/backend
python tests/test_screen_detection.py
```

Or with pytest:
```bash
python -m pytest tests/test_screen_detection.py -v
```

## Recommended Image Count Per Category
- Minimum: 3 images per category for meaningful failure rates
- Target:  10+ images per category

## Privacy Note
Do NOT commit screenshots containing sensitive information.
Use test images with publicly available or generated content only.
