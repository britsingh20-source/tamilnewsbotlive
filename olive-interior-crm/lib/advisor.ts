import {Customer,addDays,indiaToday,normalize} from './conversion';
export type Advice={sentiment:string;confidence:string;action:string;reason:string;date:string;question:string;message:string;missing:string[];evidence:string;score:number;minutes:number};
const closed=(r:Customer)=>r.archived||['Converted','Not proceeding'].includes(r.stage);
export function analyzeClient(raw:Customer,day=indiaToday()):Advice{
 const r=normalize(raw);const c=r.conversion!;
 const history=r.history.filter(h=>!Number.isNaN(Date.parse(h.date))).slice().sort((a,b)=>Date.parse(b.date)-Date.parse(a.date));
 const last=history.find(h=>/^(Interested|Price concern|Design change|No answer|Call later)(?: ·|$)/.test(h.text));
 const lastAt=last?.date||'';const outcome=last?.text.split(' ·')[0]||'';
 const recent=history.filter(h=>/^(Interested|Price concern|Design change|No answer|Call later|Voice note|Client note)/i.test(h.text)).slice(0,3);
 const noAnswer=recent.filter(h=>h.text.startsWith('No answer')).length;
 const text=(c.blocker+' '+r.notes.slice(-2500)).toLowerCase();
 const missing=[!r.name&&'customer name',!r.area&&'site area',!r.budget&&'budget range',!r.qualification?.timeline&&'start timeline',!r.notes.trim()&&'scope and decision-maker'].filter(Boolean) as string[];
 let sentiment='Not enough information',confidence='No recorded response',action=c.action,reason='Work through the current conversion stage.',question='What is your scope, budget, desired start date and who will approve the work?',minutes=15;
 const explicit=!!outcome;
 if(explicit){sentiment=outcome==='Interested'?'Interest recorded':outcome==='Price concern'?'Budget objection':outcome==='Design change'?'Design objection':outcome==='No answer'?'Unreachable · sentiment unknown':'Customer requested a later call';confidence='Recorded conversation outcome'}
 else if(/\b(too expensive|over budget|price concern|costly)\b/.test(text)){sentiment='Possible budget concern';confidence='Tentative note signal · confirm with customer'}
 else if(/\b(family approval|spouse|husband|wife|decision maker)\b/.test(text)){sentiment='Possible approval dependency';confidence='Tentative note signal · confirm with customer'}
 else if(r.qualification?.potential==='Hot'){sentiment='High interest reported by you';confidence='Your saved assessment'}
 const awaitingApproval=/\b(family approval|spouse|husband|wife|decision maker)\b/.test(text);
 let date=r.followup||day;
 if(closed(r)){action=r.stage==='Converted'?'Prepare project handover and agreed deliverables':'Respect the customer’s decision; keep sales follow-ups stopped';reason='This record is closed to conversion follow-ups.';date=''}
 else if(r.stage==='Site visit'){action=r.visit?'Attend the booked site visit and capture measurements':missing.length?'Qualify the enquiry and agree a site visit':'Agree a convenient site visit';reason=r.visit?'A site appointment is recorded.':'Site readiness and requirements must be known before preparing a useful quote.';question='Which rooms need work, what is your budget, when is the site ready and who makes the decision?';minutes=r.visit?45:15}
 else if(r.stage==='Quotation'){action='Prepare or explain the itemized quotation';reason='The site visit stage is complete; clarify scope, materials and exclusions before moving to design.';question='Does this scope fit your budget? Which items are essential and when can we review the quote together?';minutes=30}
 else if(r.stage==='3D drawing'){action=c.blocker||outcome==='Design change'?'Revise the agreed design and share the 3D viewer':'Prepare and share the 3D viewer';reason='The next deliverable is the drawing. Share it before asking for a decision.';question='Which layout, colours or storage details need changing? Agree the exact changes and a delivery date.';minutes=45}
 else{action=awaitingApproval?'Arrange a review with the decision-maker':'Review the design and quote, then agree a decision date';reason=awaitingApproval?'Your notes mention another decision-maker; resolve that dependency before pressing for confirmation.':'The customer has reached the decision stage. Identify the remaining obstacle.';question='What is still preventing you from deciding: design, scope, budget, timing or approval?'}
 if(!closed(r)&&outcome==='No answer'){action=noAnswer>=3?'Send one polite check-in and offer a convenient callback':'Retry once at a convenient time; offer a WhatsApp callback';reason=noAnswer>=3?'Repeated unanswered attempts are recorded. Avoid repeated calls; give the customer space.':'An unanswered call does not mean the customer is uninterested.';question='Is this still a good time to discuss your interiors? When would a brief call suit you?';minutes=10;if(noAnswer>=3&&date<=day)date=day}
 if(!closed(r)&&(outcome==='Price concern'||(!explicit&&sentiment==='Possible budget concern'))){action='Resolve the budget concern with scope and material options';reason='A budget concern needs a clear comparison, rather than another generic follow-up or an automatic discount.';question='What budget range is comfortable? Which items must stay, and which can be phased?'}
 if(!closed(r)&&outcome==='Interested'&&r.stage==='Follow-up'){action='Agree the final scope, decision date and confirmation step';reason='Interest was recorded, but the job is only converted after the customer explicitly confirms.';question='Is anything still unresolved? If the scope is agreed, when can we confirm the job?'}
 if(!closed(r)&&outcome==='Call later'){reason='Respect the saved callback date. Do not bring the contact forward without agreement.';action=date>day?'Wait for the agreed callback date':'Call at the agreed date and confirm the next step'}
 const overdue=date&&date<day?Math.min(30,Math.floor((Date.parse(day)-Date.parse(date))/86400000)):0;
 const score=closed(r)?-1:(date<=day?100:0)+(r.visit===day?100:0)+overdue+(r.stage==='3D drawing'?25:r.stage==='Quotation'?20:r.stage==='Follow-up'?15:0)+(outcome==='Interested'?20:0)+(c.priority==='High'?10:0)+(r.qualification?.potential==='Hot'?10:0)-(outcome==='No answer'&&noAnswer>=3?15:0);
 const name=r.name?` ${r.name}`:'';
 const message=`Hello${name}, greetings from Olive Tree Interiors. ${question} Please let me know a convenient time.`;
 return {sentiment,confidence,action,reason,date,question,message,missing,evidence:last?`${lastAt.slice(0,10)} · ${last.text.slice(0,250)}`:r.notes.trim()?`Latest note excerpt: ${r.notes.slice(-220)}`:'No conversation notes recorded yet.',score,minutes};
}
export type DayTask={id:string;clientId?:string;title:string;reason:string;steps:string;minutes:number;category:string;done:boolean;note:string};
export type DayPlan={day:string;created:string;tasks:DayTask[]};
const business=[
 ['Review ad results and choose one improvement','Record spend, WhatsApp enquiries, qualified leads and booked visits. Compare creatives using those numbers; choose one change.','Marketing',20],
 ['Prepare one customer-proof creative','Choose an approved testimonial or finished-project clip. Draft a clear hook, offer and contact prompt. Review before placing the ad.','Marketing',30],
 ['Prepare a scope comparison sheet','List materials, inclusions, exclusions and phased options so price discussions are clear.','Sales preparation',20],
 ['Check drawing delivery commitments','Review promised delivery dates and viewer links. Identify the next design work block without promising an unverified delivery.','Design preparation',20],
 ['Review the pipeline for missing facts','Capture scope, budget, site readiness, decision-maker and start date from your next conversations.','Pipeline review',15],
 ['Prepare tomorrow’s visit checklist','Prepare measurement tools and the questions needed to confirm room sizes, finishes and site readiness.','Site preparation',15],
 ['Review enquiry sources','Count qualified enquiries and conversions by source. Record the result before deciding where to spend.','Business review',15],
 ['Refresh quotation explanations','Check that material grades, payment terms and exclusions are understandable. Prepare answers to common questions.','Sales preparation',20],
 ['Organize approved portfolio references','Choose relevant kitchen, wardrobe and commercial examples that you have permission to share.','Marketing',20],
 ['Close the day and record outcomes','Save today’s client responses, promised dates and unfinished work. Tomorrow’s plan uses those records.','Daily review',15]
] as const;
export function createPlan(rows:Customer[],day=indiaToday()):DayPlan{
 const eligible=rows.filter(r=>!closed(r)).map(r=>({r,a:analyzeClient(r,day)})).filter(({a})=>a.date&&a.date<=day).sort((a,b)=>b.a.score-a.a.score||a.a.date.localeCompare(b.a.date)||a.r.id.localeCompare(b.r.id));
 const tasks:DayTask[]=eligible.slice(0,8).map(({r,a})=>({id:'client:'+r.id,clientId:r.id,title:a.action,reason:a.reason,steps:a.question,minutes:a.minutes,category:r.stage,done:false,note:''}));
 for(let i=0;tasks.length<10;i++){const b=business[i];tasks.push({id:'business:'+i,title:b[0],reason:i<2?'Keep a daily marketing work block alongside conversion work.':'Use remaining capacity to prepare the business while respecting future client callback dates.',steps:b[1],minutes:b[3],category:b[2],done:false,note:''})}
 return {day,created:new Date().toISOString(),tasks};
}
export function nextRecommendedDate(row:Customer,day=indiaToday()){
 const a=analyzeClient(row,day);if(!a.date)return '';if(a.date>day)return a.date;
 const last=[...row.history].reverse().find(h=>h.text.startsWith('No answer'));
 return addDays(day,a.sentiment.includes('Unreachable')?(last&&row.conversion!.round>=3?7:1):a.sentiment.includes('Budget')?3:row.stage==='Quotation'?2:row.stage==='3D drawing'?3:2);
}
