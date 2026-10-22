import {env} from 'cloudflare:workers';
import {getChatGPTUser} from '../../chatgpt-auth';
import {getDb} from '../../../db';
import {records} from '../../../db/schema';
import {eq,or} from 'drizzle-orm';
import {normalize,indiaToday} from '../../../lib/conversion';
import {emailOwner,phoneKey} from '../../../lib/contacts';
export async function POST(req:Request){
 const user=await getChatGPTUser();const config=env as unknown as Record<string,string>;
 const service=!user&&!!config.CRM_IMPORT_KEY&&req.headers.get('x-crm-import-key')===config.CRM_IMPORT_KEY;
 if(!user&&!service)return Response.json({error:'Sign in required'},{status:401});
 if(user&&req.headers.get('origin')!==new URL(req.url).origin)return Response.json({error:'Invalid origin'},{status:403});
 const owner=user?user.userId:emailOwner(config.CRM_OWNER_EMAIL||'');
 if(!user&&!config.CRM_OWNER_EMAIL)return Response.json({error:'Import owner is not configured'},{status:503});
 let numbers:unknown;try{numbers=(await req.json() as {numbers:unknown}).numbers}catch{return Response.json({error:'Invalid import'},{status:400})}
 if(!Array.isArray(numbers)||numbers.length>500||numbers.some(n=>typeof n!=='string'))return Response.json({error:'Send up to 500 phone numbers'},{status:400});
 const valid=[...new Set((numbers as string[]).map(phoneKey))];if(valid.some(n=>!/^[6-9]\d{9}$/.test(n)))return Response.json({error:'Each number must be an Indian 10-digit mobile number, optionally with +91.'},{status:400});
 const db=getDb();const existing=await db.select().from(records).where(user?or(eq(records.owner,user.userId),eq(records.owner,emailOwner(user.email))):eq(records.owner,owner));
 const have=new Set(existing.map(x=>phoneKey(JSON.parse(x.data).phone||'')));let added=0;
 for(const phone of valid){if(have.has(phone))continue;const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(owner+':'+phone))),v=>v.toString(16).padStart(2,'0')).join('');const row=normalize({id:'contact-'+hash,name:'',phone,area:'',service:'Home interior',source:'WhatsApp',stage:'Site visit',budget:0,followup:indiaToday(),visit:'',notes:'',quote:[],payments:[],tasks:[],qualification:{clientType:'',potential:'Not assessed' as const,timeline:''},history:[{date:new Date().toISOString(),text:'Phone number imported · name and requirements not yet added'}]});const result=await db.insert(records).values({id:row.id,owner,data:JSON.stringify(row),updated:new Date().toISOString()}).onConflictDoNothing().returning({id:records.id});added+=result.length;have.add(phone)}
 return Response.json({ok:true,added,duplicates:(numbers as string[]).length-added,total:existing.length+added});
}
