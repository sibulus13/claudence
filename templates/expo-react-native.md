# Expo / React Native — Project Instructions

## SDK Compatibility Matrix

- Always check the Expo SDK release notes before adding or upgrading RN packages
- Expo SDK 51 → react-native 0.74.x, reanimated ~3.10.1, expo-router ~3.5.x
- Expo SDK 52 → react-native 0.76.x, reanimated ~3.16.x, expo-router ~4.x
- NativeWind 4.x requires Expo SDK 52+ (RN 0.76+) for full compatibility — use with SDK 51 produces reanimated peer warnings (non-blocking in Expo Go but broken in standalone builds)

## Expo Go vs Dev Build vs Production

- **Expo Go**: scanned via QR code, zero native build required, but limited to Expo SDK's bundled native modules. OAuth uses `exp://` not custom schemes. Plaid Link SDK does NOT work in Expo Go (needs dev client)
- **Dev build**: `eas build --profile development` — unlocks custom native modules, custom URI schemes (`tarive://`), Plaid Link
- **Production**: `eas build --profile production`

## OAuth in Expo Go

- Custom URI schemes (`tarive://`) do not work for OAuth callbacks in Expo Go
- Use `AuthSession.makeRedirectUri({ path: 'auth/callback' })` without a `scheme` in Expo Go — this generates the `exp://` URL
- Detect Expo Go: `Constants.executionEnvironment === 'storeClient' || Constants.appOwnership === 'expo'`
- Register the `exp://` URL in Supabase → Authentication → URL Configuration before testing
- The `exp://` URL changes with your local IP when not using `--tunnel`; use `npx expo start --tunnel` for a stable URL (requires `@expo/ngrok` — needs an ngrok account)

## Metro Bundler (Windows)

- Run `npx expo start` directly from `apps/app` — do NOT route through Turborepo for interactive sessions (QR code gets garbled)
- First bundle is slow on Windows (Metro indexes the workspace) — subsequent starts are fast
- Port 8081 is Metro; port 3001 is the API server
- USB: `adb reverse tcp:8081 tcp:8081` and `adb reverse tcp:3001 tcp:3001` — re-run after every USB reconnect
- WiFi: set `EXPO_PUBLIC_API_BASE_URL` to your PC's LAN IP, not `localhost`
- Windows Firewall: allow Node.js on first Expo start; if accidentally blocked, re-allow via Windows Defender Firewall

## React Native Patterns

- Style props: `StyleProp<ViewStyle>` not `ViewStyle` to accept arrays
- Never add `@types/react-native` (bundled since RN 0.71)
- `process.env` is available via Metro's polyfill but TypeScript needs `@types/node` in devDependencies
- `globalThis.crypto.subtle` is available in RN 0.71+ (Hermes) — use for HMAC/SHA-256 without polyfills
- SecureStore for session persistence; falls back to localStorage on web
