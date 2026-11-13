#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$project_dir/deploy/netlify"
api_base=${FINPILOT_API_BASE_URL:-}

case "$api_base" in
  https://*) ;;
  *) echo "FINPILOT_API_BASE_URL 必須是 Render 的 HTTPS 網址" >&2; exit 2 ;;
esac
case "$api_base" in
  *localhost*|*127.0.0.1*|*127.0.0.1:*|*\[::1\]*) echo "線上前端不可指向 localhost" >&2; exit 2 ;;
esac
case "$api_base" in
  *.invalid|*.invalid/*) echo "線上前端不可指向 .invalid 保留網域" >&2; exit 2 ;;
esac

api_base=${api_base%/}
api_origin=$(printf '%s' "$api_base" | sed -E 's#^(https://[^/]+).*$#\1#')
case "$output_dir" in "$project_dir/deploy/netlify") ;; *) echo "輸出路徑驗證失敗" >&2; exit 2 ;; esac

mkdir -p "$output_dir" "$output_dir/js" "$output_dir/assets" "$output_dir/css"
find "$output_dir" -depth -mindepth 1 -delete
mkdir -p "$output_dir/js" "$output_dir/assets" "$output_dir/css"
cp "$project_dir/index.html" "$output_dir/"
cp "$project_dir"/css/*.css "$output_dir/css/"
cp "$project_dir"/js/*.js "$output_dir/js/"
cp -R "$project_dir"/assets/. "$output_dir/assets/"

cat > "$output_dir/runtime-config.js" <<EOF
window.FINPILOT_CONFIG = Object.freeze({
  apiBaseUrl: "${api_base}",
  previewMode: false,
  demoMode: true,
  accessMode: "demo-session",
  requirePreviewToken: false,
  assistantTimeoutMs: 105000
});
EOF

cat > "$output_dir/_headers" <<EOF
/*
  Cache-Control: no-store
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ${api_origin}; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
EOF
cat > "$output_dir/_redirects" <<'EOF'
/*  /index.html  200
EOF
cat > "$output_dir/robots.txt" <<'EOF'
User-agent: *
Disallow: /
EOF

echo "Netlify Live Demo 輸出已建立：$output_dir"
