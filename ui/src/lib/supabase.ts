import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

if (!url || !key) {
  throw new Error('Missing Supabase config: set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in ui/.env.local (see ui/.env.example).')
}

/** The one Supabase client for the app. PKCE keeps tokens out of the URL;
 *  /auth/callback exchanges the code itself, so automatic URL detection is off
 *  to avoid spending the single-use code twice. */
export const supabase = createClient(url, key, {
  auth: { flowType: 'pkce', detectSessionInUrl: false, persistSession: true, autoRefreshToken: true },
})
