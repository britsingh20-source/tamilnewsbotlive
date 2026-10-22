export function phoneKey(value:string){const digits=value.replace(/\D/g,'');return digits.length===12&&digits.startsWith('91')?digits.slice(2):digits}
export function emailOwner(email:string){return 'email:'+email.trim().toLowerCase()}
