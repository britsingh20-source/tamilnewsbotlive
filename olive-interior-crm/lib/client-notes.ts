import type {Customer} from './conversion';
import {phoneKey} from './contacts';
export type Suggestion={name?:string;area?:string;budget?:number;clientType?:string;potential?:'Hot'|'Warm'|'Cold';timeline?:string;service?:string};
export function extractDetails(text:string):Suggestion{
 const result:Suggestion={};
 const field=(labels:string)=>text.match(new RegExp('(?:^|[.;,\\n]|\\b)(?:'+labels+')\\s*(?::|is|=)\\s*([^.;,\\n]+)','i'))?.[1]?.trim();
 const name=field('name|client name|customer name');if(name)result.name=name;
 const area=field('area|location|address');if(area)result.area=area;
 const type=field('client type|customer type');if(type)result.clientType=type;
 const timeline=field('timeline|start date|work starts|starting');if(timeline)result.timeline=timeline;
 const budget=text.match(/\bbudget\s*(?:is|of|:|=)?\s*(?:₹|rs\.?|rupees)?\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|thousands?|k\b)?/i);
 if(budget){const n=Number(budget[1].replace(/,/g,''));const u=(budget[2]||'').toLowerCase();if(Number.isFinite(n))result.budget=n*(u.startsWith('crore')?10000000:u.startsWith('la')?100000:u.startsWith('thousand')||u==='k'?1000:1)}
 const potential=text.match(/\b(?:potential|interest)\s*(?:is|:|=)?\s*(hot|high|warm|medium|cold|low)\b|\b(high|medium|low)\s+potential\b/i);if(potential){const p=(potential[1]||potential[2]).toLowerCase();result.potential=['hot','high'].includes(p)?'Hot':['warm','medium'].includes(p)?'Warm':'Cold'}
 if(/\bmodular kitchen\b|\bkitchen only\b/i.test(text))result.service='Modular kitchen';else if(/\bcommercial|\bshop interior/i.test(text))result.service='Commercial interior';else if(/\brenovation\b/i.test(text))result.service='Renovation';else if(/\bwardrobes? only\b/i.test(text))result.service='Wardrobes';
 return result;
}
export function matchClient(text:string,rows:Customer[]){
 const numbers=[...text.matchAll(/(?:\+?91[\s-]*)?([6-9](?:[\s-]*\d){9})(?!\d)/g)].map(m=>phoneKey(m[1]));
 if(numbers.length){const matches=rows.filter(r=>numbers.includes(phoneKey(r.phone)));return matches.length===1?matches[0].id:''}
 const lower=text.toLowerCase();const matches=rows.filter(r=>r.name.trim().length>=3&&new RegExp('(?:^|[^a-z0-9])'+r.name.trim().toLowerCase().replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?:$|[^a-z0-9])','i').test(lower));return matches.length===1?matches[0].id:'';
}
export function splitNotes(text:string){return text.split(/\bnext (?:client|customer)\b|\n\s*\n/i).map(t=>t.trim()).filter(Boolean)}
export function applyDetails(row:Customer,text:string,s:Suggestion):Customer{return {...row,name:s.name??row.name,area:s.area??row.area,budget:s.budget??row.budget,service:s.service??row.service,notes:[row.notes,text].filter(Boolean).join('\n\n'),qualification:{clientType:s.clientType??row.qualification?.clientType??'',timeline:s.timeline??row.qualification?.timeline??'',potential:s.potential??row.qualification?.potential??'Not assessed'},conversion:row.conversion?{...row.conversion,priority:s.potential==='Hot'?'High':row.conversion.priority}:row.conversion,history:[...row.history,{date:new Date().toISOString(),text:'Reviewed client note added'+(s.potential?' · potential: '+s.potential:'')}]}}
