export function speechFailure(code:string){
 const messages:Record<string,string>={
  'not-allowed':'Microphone or speech permission was denied. You can use the keyboard microphone below, or allow speech access in your browser settings.',
  'service-not-allowed':'This browser did not allow its speech recognition service. Use your phone keyboard microphone, or open the CRM directly in Safari or Chrome.',
  'audio-capture':'The browser could not capture microphone audio. Close any other recording, or use your phone keyboard microphone.',
  'network':'The browser speech service could not connect. Use your phone keyboard microphone or type your note.',
  'no-speech':'No speech was detected. Try again, or use your phone keyboard microphone.',
  'language-not-supported':'The browser speech service does not support the selected language. Choose another language or use keyboard dictation.',
  'aborted':'The browser cancelled speech capture. Use the keyboard microphone or try browser capture again.'
 };
 return messages[code]||'The browser could not complete speech recognition. Use the keyboard microphone below, or open this CRM directly in Safari or Chrome.';
}
export function preferKeyboardDictation(ua:string){return /iPhone|iPad|iPod/i.test(ua)&&!/Version\/[\d.]+.*Safari\//i.test(ua)}
