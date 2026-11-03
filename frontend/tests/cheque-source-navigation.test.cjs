const assert=require('assert/strict'),fs=require('fs'),base=process.cwd(),ts=require(base+'/node_modules/typescript');
const src=fs.readFileSync('app/dashboard-client.tsx','utf8');
const code=`let state=[], cursor=0; function useState(initial){ const index=cursor++; if(!(index in state))state[index]=initial; return [state[index],v=>state[index]=v]; } function ChequeDetails(){}; const fa=n=>new Intl.NumberFormat('fa-IR').format(n);\n`+src.slice(src.indexOf('const daysToDue ='),src.indexOf('const remainingLabel ='))+src.slice(src.indexOf('const fullToman ='),src.indexOf('function RahkaranChequeTotals('))+src.slice(src.indexOf('function ChequeSourcePage('),src.indexOf('function ChequeDetails('))+`\nexport function render(props){cursor=0;return ChequeSourcePage(props)}; export function reset(){state=[];cursor=0}; export {ChequeDetails};`;
const M=require('module'),m=new M(base+'/check.cjs',module);m.paths=M._nodeModulePaths(base);m._compile(ts.transpileModule(code,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS}}).outputText,base+'/check.cjs');
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
for(const kind of ['received','issued']){
 m.exports.reset();let back=0;
 const rows=[{amount:100,days_to_due:2,source_system:'rahkaran'},{amount:200,days_to_due:-20,source_system:'karamad',branch_name:'A'},{amount:300,days_to_due:-21,source_system:'karamad',branch_name:'B'}];
 const props={kind,rows,error:'',back:()=>back++};
 let tree=m.exports.render(props),cards=walk(tree).filter(n=>n.type==='button'&&n.props.className?.includes('cheque-source-card'));
 assert.equal(cards.length,2);assert.equal(walk(tree).filter(n=>n.type===m.exports.ChequeDetails).length,0);
 for(const [index,system] of [[0,'rahkaran'],[1,'karamad']]){
  tree=m.exports.render(props);cards=walk(tree).filter(n=>n.type==='button'&&n.props.className?.includes('cheque-source-card'));
  cards[index].props.onClick();tree=m.exports.render(props);const detail=walk(tree).find(n=>n.type===m.exports.ChequeDetails);assert(detail);assert.equal(detail.props.source,system);assert(detail.props.rows.every(r=>r.source_system===system));
  assert.equal(detail.props.rows.length,system==='rahkaran'?1:kind==='issued'?1:2);
  assert.equal(detail.props.branch,system==='rahkaran'?'__rahkaran__':'');
  detail.props.back();assert.equal(walk(m.exports.render(props)).filter(n=>n.type==='button'&&n.props.className?.includes('cheque-source-card')).length,2);
 }
 walk(m.exports.render(props)).find(n=>n.type==='button'&&n.props.className==='cheque-back').props.onClick();assert.equal(back,1);
 console.log('PASS '+kind+': 2 source cards, selection, isolated rows, payable horizon, and both back paths');
}
