import {defineConfig} from 'vite';
import fs from 'node:fs';
import path from 'node:path';
const root=process.cwd();
export default defineConfig({root:'app/static',server:{host:'0.0.0.0',allowedHosts:['terminal.local']},plugins:[{
name:'recorded-engine-results',
transformIndexHtml(html){return html.replace('<main>','<div style="background:#fff1ce;padding:12px 4%;font:14px system-ui">QA preview: recorded results from the tested example PDFs. Run the Python application to compare your own documents.</div><main>')},
configureServer(server){server.middlewares.use((req,res,next)=>{
const u=new URL(req.url,'http://local'),p=u.pathname;
if(p.startsWith('/static/')){req.url=p.slice(7);return next()}
if(!p.startsWith('/api/'))return next();
const f=JSON.parse(fs.readFileSync(path.join(root,'docs/qa/fixture.json'),'utf8'));let result;
const file=(name)=>{const loc=path.join(root,'docs/qa',name);if(fs.existsSync(loc)){res.setHeader('Content-Type','image/png');fs.createReadStream(loc).pipe(res)}else{res.statusCode=404;res.end()}};
if(req.method!=='GET'){res.statusCode=501;result={detail:'This visual QA preview replays a completed real-engine comparison. Run the Python application for new jobs.'}}
else if(p==='/api/health')result={status:'ok',auth_required:false,ocr_available:false,max_upload:1073741824,chunk_size:8388608,version:'1.0.0'};
else if(p==='/api/profiles')result=f.profiles;
else if(p==='/api/jobs')result=[{...f.job,reference_name:f.job.summary.reference.name,candidate_name:f.job.summary.candidate.name}];
else if(p===`/api/jobs/${f.job.id}`)result=f.job;
else if(p.endsWith('/pages')){const sort=u.searchParams.get('sort');let data=[...f.pages];if(sort==='score')data.sort((a,b)=>(a.score??-1)-(b.score??-1));result=data.slice(+(u.searchParams.get('offset')||0),+(u.searchParams.get('offset')||0)+ +(u.searchParams.get('limit')||100))}
else if(p.endsWith('/differences')){let data=f.differences.filter(d=>(!u.searchParams.get('category')||d.category===u.searchParams.get('category'))&&(!u.searchParams.get('severity')||d.severity===u.searchParams.get('severity'))&&(!u.searchParams.has('page_pair')||d.page_pair===+u.searchParams.get('page_pair'))&&d.confidence>=+(u.searchParams.get('min_confidence')||0)&&(!u.searchParams.get('q')||JSON.stringify(d).toLowerCase().includes(u.searchParams.get('q').toLowerCase())));const offset=+(u.searchParams.get('offset')||0);result={total:data.length,items:data.slice(offset,offset+ +(u.searchParams.get('limit')||100))}}
else if(p.startsWith('/api/documents/')){const parts=p.split('/');return file(parts[3]+'-'+parts[5])}
else if(p.includes('/visual/')){const parts=p.split('/');return file(parts[5]+'-'+parts[6])}
else{res.statusCode=404;result={detail:'Not found'}}
res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result));
})}
}]});
