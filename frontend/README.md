# TurnRiverSDR - Next.js Frontend

Next.js 14 frontend for the TurnRiver SDR Agent interface. Deployed on Vercel.

## Architecture

- **Framework:** Next.js 14 App Router
- **Styling:** Tailwind CSS + shadcn/ui
- **Auth:** Supabase Auth
- **State:** React Query + Zustand
- **API:** Bedrock AgentCore REST API

## Getting Started

```bash
npm install
npm run dev
```

## Deployment

```bash
vercel --prod
```

## Environment Variables

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_AGENTCORE_API_URL=
```
