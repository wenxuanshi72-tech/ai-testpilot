# SUT Authentication Frontend Design

Status: Phase 4 implementation design

## Experience and page structure

The SUT presents a calm, precise authentication experience rather than the future Plugin's game-inspired testing workspace. The register and login routes share a two-panel AuthShell; profile is protected; the root resolves only after initialization; unknown paths use a consistent 404.

Visitor flow is register or login, authenticated profile, then logout. A direct profile visit preserves that pathname in router state so successful login returns to the intended destination.

## Component boundaries

- api/authApi.ts: typed Axios boundary, safe error normalization, request ID retention.
- auth/AuthContext.tsx: four-state session model and register/login/logout transitions.
- auth/ProtectedRoute.tsx: initialization, service error, redirect, and protected outlet.
- components/AuthShell.tsx: shared brand and form layout.
- components/FullPageStatus.tsx: perceptible initialization and retry feedback.
- pages: route-owned forms, profile, and 404 behavior.

## Authentication and data flow

AuthProvider performs one shared in-flight GET /api/auth/me during initialization. A public user response becomes authenticated; HTTP 401 becomes unauthenticated; network/service failure becomes error. Cleanup guards prevent stale effect updates. Register and login set the returned public user; logout clears frontend state even when the network request fails.

Axios uses credentials, an eight-second timeout, and VITE_SUT_API_BASE_URL with a safe loopback default. The browser owns the HttpOnly cookie. No token is read from or written to browser storage. UI errors use reviewed safe messages, field mappings, and optional request IDs rather than backend internal text.

## Visual system

Tokens define primary #176b87, success #23856d, error #c2414b, ink/surface/canvas colors, 10/24px radii, 44px controls, a system-first Inter stack, six spacing levels, and restrained card shadows. Desktop authentication uses a brand/form split; below 800px the brand panel compacts and the form becomes a single-column surface. Content remains usable from 320px without horizontal scrolling.

## Accessibility and states

Pages have named main landmarks, hierarchical headings, document titles, form labels, explicit actions, visible focus rings, linked field errors, live loading/error feedback, and non-color session text. Password controls use correct autocomplete. Reduced-motion preferences collapse animations and transitions.

Loading exists at initialization, protected-route restoration, and every mutation. Empty authentication becomes a login redirect. Recoverable initialization errors provide retry; API errors provide safe feedback and request IDs.

## Protected seeded defect

REQ-AUTH-USERNAME-001 still requires six characters. Phase 4 intentionally omits only the username minimum-length UI rule so z1234 / Test1234 reaches the real registration API. Required, allowed-character, trimming, maximum-length, password, confirmation, and duplicate-submit controls remain active. This is protected BUG-AUTH-001 behavior, not a corrected requirement.
