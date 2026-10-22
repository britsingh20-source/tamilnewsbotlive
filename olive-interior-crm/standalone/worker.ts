import assets from '../.standalone-build/assets.json';
import {normalize,indiaToday} from '../lib/conversion';
import {phoneKey} from '../lib/contacts';
import {customerSchema} from './customer-schema';
import {auth} from './auth';
import {dailyPlan,plannerApi} from './planner';
const owner='owner';
const headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','Permissions-Policy':'microphone=(self)'};
function json(body:unknown,status=200){return Response.json(body,{status,headers})}
export default {
 async scheduled(_event:ScheduledController,env:StandaloneEnv,_ctx:ExecutionContext){await dailyPlan(env);},
 async fetch(request:Request,env:StandaloneEnv,_ctx:ExecutionContext):Promise<Response>{
  const url=new URL(request.url);
  try{
   if(url.pathname==='/health')return json({app:'Olive Tree Interior CRM',hosting:'Cloudflare Workers',protected:true});
   const login=await auth(request,env);if(login)return login;
   if(url.pathname.startsWith('/api/')){
    if(request.method==='POST'&&request.headers.get('origin')!==url.origin)return json({error:'Invalid origin'},403);
    if(request.method==='POST'&&Number(request.headers.get('content-length')||0)>120000)return json({error:'Request too large'},413);
    if(url.pathname==='/api/plan')return plannerApi(request,env);
    if(url.pathname==='/api/records'&&request.method==='GET'){
     const result=await env.DB.prepare('SELECT data,updated FROM crm_records WHERE owner=?').bind(owner).all<{data:string;updated:string}>();return json(result.results.map(r=>normalize(JSON.parse(r.data),r.updated.slice(0,10))));
    }
    if(url.pathname==='/api/records'&&request.method==='POST'){
     let row;try{row=normalize(customerSchema.parse(await request.json()))}catch{return json({error:'Check customer details and try again.'},400)}
     if(JSON.stringify(row).length>100000||(!row.name.trim()&&!/^[6-9]\d{9}$/.test(phoneKey(row.phone))))return json({error:'Enter a customer name or a valid mobile number.'},400);
     const existing=await env.DB.prepare('SELECT id,data FROM crm_records WHERE owner=?').bind(owner).all<{id:string;data:string}>();
     if(row.phone&&existing.results.some(r=>r.id!==row.id&&phoneKey(JSON.parse(r.data).phone||'')===phoneKey(row.phone)))return json({error:'This phone number already exists. Open that customer to update it.'},409);
     const other=await env.DB.prepare('SELECT owner FROM crm_records WHERE id=?').bind(row.id).first<{owner:string}>();if(other&&other.owner!==owner)return json({error:'Not allowed'},403);
     await env.DB.prepare('INSERT INTO crm_records(id,owner,data,updated) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated WHERE crm_records.owner=excluded.owner').bind(row.id,owner,JSON.stringify(row),new Date().toISOString()).run();return json({ok:true});
    }
    if(url.pathname==='/api/import'&&request.method==='POST'){
     let numbers:unknown;try{numbers=(await request.json() as {numbers:unknown}).numbers}catch{return json({error:'Invalid import'},400)}
     if(!Array.isArray(numbers)||numbers.length>500||numbers.some(n=>typeof n!=='string'))return json({error:'Send up to 500 phone numbers'},400);
     const clean=[...new Set((numbers as string[]).map(phoneKey))];if(clean.some(n=>!/^[6-9]\d{9}$/.test(n)))return json({error:'Each contact needs a valid Indian mobile number.'},400);
     const existing=await env.DB.prepare('SELECT data FROM crm_records WHERE owner=?').bind(owner).all<{data:string}>();const have=new Set(existing.results.map(r=>phoneKey(JSON.parse(r.data).phone||'')));let added=0;
     for(const phone of clean){if(have.has(phone))continue;const id='phone-'+phone;const row=normalize({id,name:'',phone,area:'',service:'Home interior',source:'WhatsApp',stage:'Site visit',budget:0,followup:indiaToday(),visit:'',notes:'',quote:[],payments:[],tasks:[],qualification:{clientType:'',potential:'Not assessed' as const,timeline:''},history:[{date:new Date().toISOString(),text:'Phone number imported'}]});const result=await env.DB.prepare('INSERT OR IGNORE INTO crm_records(id,owner,data,updated) VALUES(?,?,?,?)').bind(id,owner,JSON.stringify(row),new Date().toISOString()).run();added+=result.meta.changes;have.add(phone)}
     return json({ok:true,added,duplicates:numbers.length-added,total:existing.results.length+added});
    }
    return json({error:'Not found'},404);
   }
   if(request.method!=='GET'&&request.method!=='HEAD')return new Response('Method not allowed',{status:405,headers});
   const path=url.pathname==='/'?'/index.html':url.pathname;const asset=(assets as Record<string,{mime:string;body:string}>)[path];if(!asset)return new Response('Not found',{status:404,headers});
   return new Response(request.method==='HEAD'?null:asset.body,{headers:{...headers,'Content-Type':asset.mime,'Cache-Control':path.startsWith('/assets/')?'private, max-age=31536000, immutable':'no-store'}});
  }catch(error){console.error(JSON.stringify({event:'crm_request_failed',path:url.pathname,error:error instanceof Error?error.message:'unknown'}));return json({error:'Could not complete this request. Please try again.'},500)}
 }
};
