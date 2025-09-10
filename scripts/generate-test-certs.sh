#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE_DIR="$BASE_DIR/tests/fixtures"
CERTS_DIR="$EXAMPLE_DIR/certs"
EXCLUDE_DIR="$CERTS_DIR/exclude"
PFX_DIR="$CERTS_DIR/pfx"

mkdir -p "$CERTS_DIR" "$EXCLUDE_DIR" "$PFX_DIR"

# -----------------------------
#   CA & Chain Setup
# -----------------------------
ROOT_CA_KEY="$CERTS_DIR/rootCA.key"
ROOT_CA_CERT="$CERTS_DIR/rootCA.pem"
INT_CA_KEY="$CERTS_DIR/intermediate.key"
INT_CA_CERT="$CERTS_DIR/intermediate.pem"
CA_CHAIN="$CERTS_DIR/ca-chain.pem"

CA_CERT="$INT_CA_CERT"
CA_KEY="$INT_CA_KEY"

# PFX Config Defaults
ITERATIONS=2000
MACALG="sha1"
KEYPBE="PBE-SHA1-3DES"
CERTPBE="PBE-SHA1-3DES"
MACSALT=20
CSP_NAME="Microsoft Enhanced Cryptographic Provider v1.0"

# -----------------------------
#   Generate Root CA
# -----------------------------
if [[ ! -f "$ROOT_CA_CERT" ]]; then
    echo "🔹 Generating Root CA..."
    openssl genrsa -out "$ROOT_CA_KEY" 4096 2>/dev/null
    openssl req -x509 -new -nodes -key "$ROOT_CA_KEY" \
        -sha256 -days 3650 \
        -subj "/CN=Root CA" \
        -out "$ROOT_CA_CERT" 2>/dev/null
fi

# -----------------------------
#   Generate Intermediate CA
# -----------------------------
if [[ ! -f "$INT_CA_CERT" ]]; then
    echo "🔹 Generating Intermediate CA..."
    openssl genrsa -out "$INT_CA_KEY" 4096 2>/dev/null
    openssl req -new -key "$INT_CA_KEY" \
        -subj "/CN=Intermediate CA" \
        -out "$CERTS_DIR/intermediate.csr" 2>/dev/null
    openssl x509 -req \
        -in "$CERTS_DIR/intermediate.csr" \
        -CA "$ROOT_CA_CERT" \
        -CAkey "$ROOT_CA_KEY" \
        -CAcreateserial \
        -out "$INT_CA_CERT" \
        -days 1825 \
        -sha256 2>/dev/null
    rm -f "$CERTS_DIR/intermediate.csr"
fi

cat "$INT_CA_CERT" "$ROOT_CA_CERT" > "$CA_CHAIN"

# -----------------------------
#   Helper Function
# -----------------------------
generate_cert() {
    local name=$1
    local cn=$2
    local days=$3
    local key_size=${4:-2048}
    local extra_ext=${5:-}

    local key_file="$CERTS_DIR/${name}.key"
    local csr_file="$CERTS_DIR/${name}.csr"
    local crt_file="$CERTS_DIR/${name}.crt"

    openssl genrsa -out "$key_file" "$key_size" 2>/dev/null

    openssl req -new \
        -key "$key_file" \
        -out "$csr_file" \
        -subj "/CN=${cn}" 2>/dev/null

    openssl x509 -req \
        -in "$csr_file" \
        -CA "$CA_CERT" \
        -CAkey "$CA_KEY" \
        -CAcreateserial \
        -out "$crt_file" \
        -days "$days" \
        -sha256 \
        $extra_ext 2>/dev/null

    rm -f "$csr_file"
}

# -----------------------------
#   1. Excluded Directory Certs
# -----------------------------
echo "🔹 Generating excluded directory certs..."
generate_cert "exclude/test1" "exclude-test1.example.com" 365
generate_cert "exclude/test2" "exclude-test2.example.com" 365

# -----------------------------
#   2. SAN Certificates
# -----------------------------
echo "🔹 Generating SAN certs..."
for i in 1 2; do
    san_ext=$(mktemp)
    echo "subjectAltName=DNS:san${i}.example.com,DNS:alt${i}.example.com" > "$san_ext"
    generate_cert "san_cert_${i}" "san${i}.example.com" 365 2048 "-extfile $san_ext"
    rm -f "$san_ext"
done

# -----------------------------
#   3. Fake Amazon CA & Cert
# -----------------------------
echo "🔹 Generating fake Amazon CA cert..."
generate_cert "fake_amazon" "amazonaws.com" 730

# -----------------------------
#   4. Fake DigiCert CA & Cert
# -----------------------------
echo "🔹 Generating fake DigiCert CA cert..."
generate_cert "fake_digicert" "digicert.com" 730

# -----------------------------
#   5. Weak Algorithm Certs (MD5, SHA1)
# -----------------------------
echo "🔹 Generating weak algorithm certs..."
for alg in md5 sha1; do
    key_file="$CERTS_DIR/weak_alg_${alg}.key"
    csr_file="$CERTS_DIR/weak_alg_${alg}.csr"
    crt_file="$CERTS_DIR/weak_alg_${alg}.crt"

    openssl genrsa -out "$key_file" 2048 2>/dev/null
    openssl req -new -key "$key_file" -out "$csr_file" -subj "/CN=weak-${alg}.example.com" 2>/dev/null
    openssl x509 -req -in "$csr_file" -CA "$CA_CERT" -CAkey "$CA_KEY" \
        -CAcreateserial -out "$crt_file" -days 365 -$alg 2>/dev/null
    rm -f "$csr_file"
done

# -----------------------------
#   6. Weak Key Certs (512 & 1024)
# -----------------------------
echo "🔹 Generating weak key certs..."
generate_cert "weak_key_512" "weak-key-512.example.com" 365 512
generate_cert "weak_key_1024" "weak-key-1024.example.com" 365 1024

# -----------------------------
#   7. Short Expiration Certs (1-day)
# -----------------------------
echo "🔹 Generating short-lived certs..."
generate_cert "short_expire" "short-expire.example.com" 1

# -----------------------------
#   8. Duplicate Certificates
# -----------------------------
echo "🔹 Generating duplicate certs..."
generate_cert "duplicate_1" "duplicate.example.com" 365
cp "$CERTS_DIR/duplicate_1.crt" "$CERTS_DIR/duplicate_2.crt"
cp "$CERTS_DIR/duplicate_1.key" "$CERTS_DIR/duplicate_2.key"

# -----------------------------
#   9. 1-Year Valid Certificates
# -----------------------------
echo "🔹 Generating 1-year valid certs..."
for i in 1 2 3; do
    generate_cert "1yr_valid_${i}" "1yr-valid-${i}.example.com" 365
done

# -----------------------------
#   Windows-Compatible PFX Files
# -----------------------------
echo "🔹 Generating Windows-compatible PFX files..."
for i in 1 2 3; do
    key_file="$PFX_DIR/p12_cert_${i}.key"
    pem_file="$PFX_DIR/p12_cert_${i}.pem"
    pfx_file="$PFX_DIR/p12_cert_${i}.pfx"
    cn="p12cert${i}.example.com"
    friendly_name=$(echo "$cn" | sed 's/\./_/g')

    openssl genrsa -out "$key_file" 2048 2>/dev/null
    openssl req -new -key "$key_file" \
        -out "$PFX_DIR/p12_cert_${i}.csr" \
        -subj "/CN=$cn" 2>/dev/null
    openssl x509 -req -in "$PFX_DIR/p12_cert_${i}.csr" \
        -CA "$CA_CERT" -CAkey "$CA_KEY" \
        -CAcreateserial -out "$pem_file" \
        -days 365 -sha256 2>/dev/null

    rm -f "$PFX_DIR/p12_cert_${i}.csr"

    case $i in
        1) PFX_PASS="changeit" ;;
        2) PFX_PASS="password" ;;
        3) PFX_PASS="123456" ;;
    esac

    openssl pkcs12 -export \
        -inkey "$key_file" \
        -in "$pem_file" \
        -out "$pfx_file" \
        -password pass:"$PFX_PASS" \
        -name "$friendly_name" 2>/dev/null
done

echo "🔓 Setting world-readable permissions on all certs..."
chmod 644 "$CERTS_DIR"/*.pem 2>/dev/null || true
chmod 644 "$CERTS_DIR"/pfx/*.pfx 2>/dev/null || true
chmod 644 "$CERTS_DIR"/exclude/*.pem 2>/dev/null || true

echo "✅ All test certificates successfully generated in: $CERTS_DIR"