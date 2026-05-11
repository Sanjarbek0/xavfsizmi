# Seeding the Pwned Passwords R2 bucket

Cloudflare Worker `@xavfsizmi/worker` answers k-anonymity password lookups by
streaming a single SHA-1 prefix file out of R2 (see `apps/worker/src/index.ts`).
The file layout matches the public Pwned Passwords v8 release:

```
{prefix}.txt        # 16² × 16² = 1,048,576 files
                    # e.g. 21BD1.txt
```

Each file contains lines of the form `SUFFIX:COUNT` (35-char SHA-1 suffix and
a decimal hit count) sorted by suffix.

## 1. Create the R2 buckets

```bash
# One-time, in the worker app:
cd apps/worker

pnpm exec wrangler r2 bucket create xavfsizmi-pwned-passwords
pnpm exec wrangler r2 bucket create xavfsizmi-pwned-passwords-dev
```

## 2. Download the latest hash dump

The official downloader keeps a local copy of every prefix file. The first run
fetches ~38 GB (SHA-1, ordered by hash), subsequent runs only fetch deltas.

```bash
# Pick a host with fast bandwidth + enough disk.
mkdir -p ~/pwned-passwords && cd ~/pwned-passwords

# https://github.com/HaveIBeenPwned/PwnedPasswordsDownloader
dotnet tool install --global haveibeenpwned-downloader
haveibeenpwned-downloader -s -o pwned-passwords
# Output: ~1,048,576 files named 00000.txt … FFFFF.txt
```

## 3. Upload to R2 in parallel

R2 supports the S3 API; configure rclone once and let it sync the whole tree.

```bash
# ~/.config/rclone/rclone.conf
[r2]
type = s3
provider = Cloudflare
access_key_id = <R2_ACCESS_KEY_ID>
secret_access_key = <R2_SECRET_ACCESS_KEY>
endpoint = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
acl = private

# 1M small files — keep concurrency reasonable.
rclone copy \
    --transfers 32 \
    --checkers 64 \
    --s3-chunk-size 16M \
    --s3-upload-concurrency 4 \
    ~/pwned-passwords/pwned-passwords \
    r2:xavfsizmi-pwned-passwords
```

## 4. Deploy the worker

```bash
cd apps/worker
pnpm exec wrangler deploy --env production
```

Smoke test (replace `passwords.xavfsizmi.example` with the deployed host):

```bash
# The test prefix "21BD1" is part of the public HIBP example for "password".
curl -sf https://passwords.xavfsizmi.example/range/21BD1 | head -3
```

## 5. Keeping the dataset fresh

HIBP publishes deltas about once a month. Re-run steps 2 + 3 monthly (you can
schedule this on a small Hetzner VPS via cron). The downloader detects file
hashes and only re-downloads what actually changed.
