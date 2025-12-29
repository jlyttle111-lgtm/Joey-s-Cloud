# Joey's Cloud

A personal cloud storage server with file management, user authentication, and admin features. Built with Flask.

## Features

- 🗂️ **File Management**: Upload, download, organize files and folders
- 📁 **Chunked Folder Upload**: Upload entire folders with progress tracking
- 👤 **User System**: Multi-user support with isolated storage
- 🔐 **Authentication**: Secure login and registration
- 👨‍💼 **Admin Panel**: User management and storage statistics
- 🎨 **Modern UI**: Clean glass morphism design
- 📊 **Storage Stats**: Track usage and disk space

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

1. Clone or download this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On Linux/Mac:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set environment variables (optional, but recommended):
   ```bash
   # Windows (PowerShell):
   $env:ADMIN_USER="your_admin_username"
   $env:ADMIN_PASS="your_secure_password"
   $env:FLASK_SECRET_KEY="your-secret-key-here"
   $env:FLASK_DEBUG="false"
   
   # Linux/Mac:
   export ADMIN_USER="your_admin_username"
   export ADMIN_PASS="your_secure_password"
   export FLASK_SECRET_KEY="your-secret-key-here"
   export FLASK_DEBUG="false"
   ```

5. Run the server:
   ```bash
   python app.py
   ```

6. Open your browser to `http://localhost:8000`

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_USER` | `joey` | Admin username |
| `ADMIN_PASS` | `change-me-now` | Admin password (⚠️ **CHANGE THIS!**) |
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | Secret key for sessions (⚠️ **CHANGE THIS!**) |
| `FLASK_DEBUG` | `true` | Debug mode (set to `false` in production) |
| `MAX_UPLOAD_BYTES` | `21474836480` (20GB) | Maximum upload size in bytes |
| `MAX_FORM_MEMORY_SIZE` | `67108864` (64MB) | Maximum form data in memory |

### Upload Limits

Default maximum upload is 20GB. To change:

```bash
# Set to 50GB
export MAX_UPLOAD_BYTES=$((50*1024*1024*1024))
```

## Project Structure

```
mini_cloud/
├── app.py              # Main application file
├── requirements.txt    # Python dependencies
├── data/              # Database and data files
│   ├── cloud.db       # SQLite database
│   ├── metrics.json   # Usage metrics (if implemented)
│   └── notes.json     # Notes data (if implemented)
├── storage/           # User file storage
│   └── user_{id}/     # Per-user directories
└── venv/              # Virtual environment (gitignored)
```

## Usage

### First Time Setup

1. The default admin account is created automatically:
   - Username: `joey` (or `ADMIN_USER` env var)
   - Password: `change-me-now` (or `ADMIN_PASS` env var)
   - **⚠️ Change this password immediately!**

2. Register new users or use the admin account

### Features

#### File Operations
- **Upload Single File**: Select a file and upload
- **Upload Folder**: Upload entire directory structure (best in Chrome/Edge/Brave)
- **Create Folder**: Make new directories
- **Delete**: Remove files or folders
- **Rename**: Rename files and folders
- **Download**: Click on files to download

#### Admin Features
- View all users' storage usage
- Monitor disk space
- User management (via database)

## Production Deployment

### Security Checklist

- [ ] Set `FLASK_DEBUG=false`
- [ ] Generate secure `FLASK_SECRET_KEY` (use `secrets.token_hex(32)`)
- [ ] Change default admin credentials
- [ ] Use HTTPS (reverse proxy with nginx/caddy)
- [ ] Set up firewall rules
- [ ] Enable rate limiting
- [ ] Set up automated backups
- [ ] Configure log rotation

### Using Gunicorn (Production)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Using Systemd (Linux)

Create `/etc/systemd/system/joey-cloud.service`:

```ini
[Unit]
Description=Joey's Cloud Server
After=network.target

[Service]
User=your_user
WorkingDirectory=/path/to/mini_cloud
Environment="PATH=/path/to/mini_cloud/venv/bin"
ExecStart=/path/to/mini_cloud/venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable joey-cloud
sudo systemctl start joey-cloud
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Development

### Adding Features

The application is currently a single-file Flask app. To add features:

1. Notes system (data structure exists in `data/notes.json`)
2. Metrics tracking (structure exists in `data/metrics.json`)
3. File sharing with temporary links
4. Search functionality
5. API keys for programmatic access

See `CODE_REVIEW.md` for detailed suggestions.

### Code Structure

- Routes: Defined with `@app.route()`
- Database: SQLite via `db()` function
- Storage: Per-user directories in `storage/user_{id}/`
- UI: Embedded HTML/CSS/JS in `APP_HTML` template

## Troubleshooting

### Upload Fails with 413 Error
- Increase `MAX_UPLOAD_BYTES` environment variable
- Check reverse proxy upload limits (if using nginx)

### Can't Access Files
- Check file permissions: `chmod -R 755 storage/`
- Verify user storage directory exists

### Database Errors
- Ensure `data/` directory is writable
- Check disk space
- Verify SQLite file permissions

## License

Personal use project. Modify as needed.

## Support

For issues or questions, refer to `CODE_REVIEW.md` for improvement suggestions.

---

**Version**: 1.0
**Last Updated**: 2025-01-26

"# Joey-s-Cloud" 

