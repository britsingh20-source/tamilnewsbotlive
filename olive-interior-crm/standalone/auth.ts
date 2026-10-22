const age=90*24*60*60;
export async function digest(value:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),b=>b.toString(16).padStart(2,'0')).join('')}
export async function passwordHash(password:string,salt:string){const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveBits']);return new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2',salt:new TextEncoder().encode(salt),iterations:100000,hash:'SHA-256'},key,256))}
function equal(a:Uint8Array,b:Uint8Array){let diff=a.length^b.length;for(let i=0;i<a.length;i++)diff|=a[i]^(b[i]??0);return diff===0}
const page=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · Olive Tree CRM</title><style>*{box-sizing:border-box}body{margin:0;background:#f5f6f1;color:#26392f;font:17px system-ui;display:grid;place-items:center;min-height:100dvh;padding:24px}main{background:white;padding:32px;border-radius:24px;width:100%;max-width:410px;box-shadow:0 12px 60px #26392f12}h1{font-size:28px}label{display:block;margin-bottom:8px}input,button{width:100%;font:inherit;padding:15px;border-radius:12px;border:1px solid #cdd5c8}button{background:#49653d;color:white;margin-top:18px;font-weight:600;cursor:pointer}p{line-height:1.6;color:#687460}#error{color:#a33422}small{color:#687460}</style><main><small>OLIVE TREE INTERIORS</small><h1>Your customer workspace</h1><form id="login"><label for="password">Password</label><input id="password" type="password" name="password" autocomplete="current-password" required autofocus><button>Open CRM</button><p id="error" role="alert"></p></form><p>Stay signed in on this device for 90 days.</p></main><script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();const button=document.querySelector('button');button.disabled=true;try{const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.querySelector('input').value})});if(r.ok){location.replace('/')}else{document.querySelector('#error').textContent=(await r.json()).error}}catch{document.querySelector('#error').textContent='Unable to connect. Please try again.'}finally{button.disabled=false}};</script></html>`;
export async function auth(request:Request,env:StandaloneEnv):Promise<Response|null>{
 const url=new URL(request.url);const now=Math.floor(Date.now()/1000);const headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'};
 const json=(error:string,status:number)=>Response.json({error},{status,headers});
 if(url.pathname==='/auth/login'&&request.method==='POST'){
  if(request.headers.get('origin')!==url.origin)return json('Invalid origin',403);
  if(Number(request.headers.get('content-length')||0)>2048)return json('Request too large',413);
  const ip=await digest(request.headers.get('cf-connecting-ip')||'unknown');
  const attempts=await env.DB.prepare('INSERT INTO crm_login_attempts(ip,attempts,reset) VALUES(?,1,?) ON CONFLICT(ip) DO UPDATE SET attempts=CASE WHEN reset<=? THEN 1 ELSE attempts+1 END,reset=CASE WHEN reset<=? THEN excluded.reset ELSE reset END RETURNING attempts').bind(ip,now+900,now,now).first<{attempts:number}>();
  if(!attempts||attempts.attempts>10)return json('Too many attempts. Try again in 15 minutes.',429);
  let password:string;try{const body=await request.json() as {password?:unknown};if(typeof body.password!=='string'||body.password.length>256)return json('Incorrect password.',401);password=body.password}catch{return json('Enter your password.',400)}
  const [salt,hash]=env.CRM_PASSWORD_HASH.split(':');if(!salt||!hash)throw Error('Password configuration missing');
  const actual=await passwordHash(password,salt);const expected=Uint8Array.from(hash.match(/.{2}/g)??[],x=>parseInt(x,16));if(!equal(actual,expected))return json('Incorrect password.',401);
  const token=Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
  await env.DB.batch([env.DB.prepare('DELETE FROM crm_sessions WHERE expires<=?').bind(now),env.DB.prepare('DELETE FROM crm_login_attempts WHERE ip=? OR reset<=?').bind(ip,now),env.DB.prepare('INSERT INTO crm_sessions(token,expires) VALUES(?,?)').bind(await digest(token),now+age)]);
  return Response.json({ok:true},{headers:{...headers,'Set-Cookie':`__Host-crm_session=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${age}`}});
 }
 if(url.pathname==='/login'&&request.method==='GET')return new Response(page,{headers:{...headers,'Content-Type':'text/html; charset=utf-8'}});
 const token=request.headers.get('cookie')?.match(/(?:^|;\s*)__Host-crm_session=([a-f0-9]{64})(?:;|$)/)?.[1];
 if(token){const session=await env.DB.prepare('SELECT expires FROM crm_sessions WHERE token=? AND expires>?').bind(await digest(token),now).first();if(session)return null}
 if(url.pathname.startsWith('/api/'))return json('Please unlock the CRM.',401);
 return new Response(null,{status:303,headers:{...headers,Location:'/login'}});
}
