import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'Olive Tree | Interior CRM',description:'A simple conversion follow-up CRM: site visit, quotation, 3D drawing and confirmation'};
export default function Layout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body>{children}</body></html>}
