import {createPlan,DayPlan} from '../lib/advisor';
import {Customer,indiaToday} from '../lib/conversion';
export async function dailyPlan(env:StandaloneEnv,day=indiaToday()):Promise<DayPlan>{
 const existing=await env.DB.prepare('SELECT data FROM crm_daily_plans WHERE day=?').bind(day).first<{data:string}>();if(existing)return JSON.parse(existing.data);
 const rows=await env.DB.prepare('SELECT data FROM crm_records WHERE owner=?').bind('owner').all<{data:string}>();
 const plan=createPlan(rows.results.map(r=>JSON.parse(r.data) as Customer),day);
 await env.DB.prepare('INSERT OR IGNORE INTO crm_daily_plans(day,data) VALUES(?,?)').bind(day,JSON.stringify(plan)).run();
 const saved=await env.DB.prepare('SELECT data FROM crm_daily_plans WHERE day=?').bind(day).first<{data:string}>();return JSON.parse(saved!.data);
}
export async function plannerApi(request:Request,env:StandaloneEnv):Promise<Response>{
 const plan=await dailyPlan(env);const headers={'Cache-Control':'no-store'};
 if(request.method==='GET')return Response.json(plan,{headers});
 if(request.method!=='POST')return Response.json({error:'Method not allowed'},{status:405,headers});
 let body:{id?:string;done?:boolean;note?:string;replan?:boolean};try{body=await request.json()}catch{return Response.json({error:'Invalid update'},{status:400,headers})}
 if(body.replan===true){
  const rows=await env.DB.prepare('SELECT data FROM crm_records WHERE owner=?').bind('owner').all<{data:string}>();const fresh=createPlan(rows.results.map(r=>JSON.parse(r.data)),plan.day);
  // Preserve completed work and progress. Explicit refresh only replaces unfinished assignments.
  const done=plan.tasks.filter(t=>t.done);const tasks=[...done,...fresh.tasks.filter(t=>!done.some(d=>d.id===t.id))].slice(0,10).map(t=>({...t,note:plan.tasks.find(p=>p.id===t.id)?.note||t.note}));
  const changed=await env.DB.prepare("UPDATE crm_daily_plans SET data=json_set(data,'$.tasks',json(?)) WHERE day=? AND data=?").bind(JSON.stringify(tasks),plan.day,JSON.stringify(plan)).run();
  if(!changed.meta.changes)return Response.json({error:'The plan changed on another device. Reload and try again.'},{status:409,headers});
 }else{
  const index=plan.tasks.findIndex(t=>t.id===body.id);if(index<0||typeof body.done!=='boolean'||typeof body.note!=='string'||body.note.length>2000)return Response.json({error:'Invalid task update'},{status:400,headers});
  await env.DB.prepare('UPDATE crm_daily_plans SET data=json_set(data,?,json(?),?,?) WHERE day=?').bind(`$.tasks[${index}].done`,JSON.stringify(body.done),`$.tasks[${index}].note`,body.note,plan.day).run();
 }
 return Response.json(await dailyPlan(env),{headers});
}
