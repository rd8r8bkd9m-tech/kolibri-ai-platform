#!/bin/bash
# Kolibri AI - SSL/TLS Setup with Let's Encrypt
# Usage: ./setup-ssl.sh <domain> <email>

set -e

DOMAIN=${1:-"kolibri.ai"}
EMAIL=${2:-"admin@kolibri.ai"}

echo "Setting up SSL for $DOMAIN..."

install_certbot() {
    if ! command -v certbot &> /dev/null; then
        echo "Installing certbot..."
        apt-get update
        apt-get install -y certbot python3-certbot-nginx
    fi
}

obtain_certificate() {
    echo "Obtaining SSL certificate..."
    certbot --nginx \
        -d "$DOMAIN" \
        -d "www.$DOMAIN" \
        --non-interactive \
        --agree-tos \
        --email "$EMAIL" \
        --redirect
}

setup_renewal() {
    echo "Setting up auto-renewal..."
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
}

update_nginx() {
    echo "Updating Nginx configuration..."
    cat > /etc/nginx/sites-available/kolibri-ssl << 'EOF'
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name DOMAIN_PLACEHOLDER;

    ssl_certificate /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Frontend
    location / {
        root /opt/kolibri-ai/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    # Cluster
    location /cluster/ {
        proxy_pass http://127.0.0.1:9001;
        proxy_set_header Host $host;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
EOF

    sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" /etc/nginx/sites-available/kolibri-ssl
    ln -sf /etc/nginx/sites-available/kolibri-ssl /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
}

main() {
    install_certbot
    obtain_certificate
    setup_renewal
    update_nginx
    echo "SSL setup complete for $DOMAIN"
    echo "Certificate will auto-renew via cron"
}

main
