# Report WeasyPrint

Adds WeasyPrint PDF rendering support to Odoo PDF reports.

## Requirements

System packages (Debian/Ubuntu example):

```bash
sudo apt install -y \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info \
    fonts-dejavu-core fonts-liberation
```

Python:
```
pip3 install WeasyPrint>=66.0
```

## Usage

Enable *Render with WeasyPrint* on any report (Settings → Technical → Reports).
