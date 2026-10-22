// Standalone Worker bindings. Database types come from @cloudflare/workers-types.
interface StandaloneEnv {
  DB: D1Database;
  OWNER_EMAIL: string;
}
