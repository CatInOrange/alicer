# Alicer

Alicer is a Flutter companion app with a chat-first home screen, time journals,
and a Tavern-style prompt configuration page.

## Android release flow

Android APK builds are done by GitHub Actions, following the AliceChat release
pattern:

- Push to `main`, or run the workflow manually.
- GitHub Actions restores the Android upload keystore from repository secrets.
- The workflow builds a release APK, compresses it, generates `latest.json`, and
  uploads both to Tencent COS.
- The app update screen reads:
  `https://yzcos-1317705976.cos.ap-singapore.myqcloud.com/alicer/apk/latest.json`

Required GitHub repository secrets:

- `ALICER_UPLOAD_KEYSTORE_BASE64`
- `ALICER_UPLOAD_STORE_PASSWORD`
- `ALICER_UPLOAD_KEY_ALIAS`
- `ALICER_UPLOAD_KEY_PASSWORD`
- `COS_BUCKET`
- `COS_REGION`
- `COS_SECRET_ID`
- `COS_SECRET_KEY`

The local `android/key.properties` and `android/upload-keystore.p12` files are
ignored by git and should not be committed.

After GitHub CLI is authenticated, configure repository secrets with:

```bash
export COS_BUCKET=...
export COS_REGION=...
export COS_SECRET_ID=...
export COS_SECRET_KEY=...
./scripts/configure_github_secrets.sh CatInOrange/alicer
```
