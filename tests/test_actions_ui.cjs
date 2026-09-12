const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.style={};this.classList={add(){},remove(){}};this.listeners={};}
  appendChild(e){this.children.push(e);return e;} prepend(e){this.children.unshift(e);}
  replaceChildren(...items){this.children=items;if(this.tag==='select')this.value='';}
  add(e){this.appendChild(e);if(!this.value)this.value=e.value;} setAttribute(){}
  addEventListener(n,f){this.listeners[n]=f;} removeEventListener(n){delete this.listeners[n];}
  showModal(){this.open=true;} close(){this.open=false;this.listeners.close?.();}
}
(async()=>{
 const elements={};const document={getElementById:id=>elements[id]??=(new Element(id==='action-select'?'select':'div')),
 createElement:tag=>new Element(tag),addEventListener(){}};
 let ready,selectionEvent,selected={row:0,column:0,rows:2,columns:1},sent;
 const writes=[],fills=[];
 const sheet={id:'sheet-one',onChanged:{add(){}},onFormatChanged:{add(){}},load(){},getRangeByIndexes(r,c,rows,cols){
   return {load(){},valueTypes:Array.from({length:rows},()=>Array(cols).fill('Double')),conditionalFormats:{load(){},items:[]},
     get values(){return Array.from({length:rows},(_,i)=>Array(cols).fill(i+10));},set values(v){writes.push(v);},
     formulas:Array.from({length:rows},()=>Array(cols).fill('')),address:`Sheet1!${r},${c}`,
     getCell(r,c){return {format:{fill:{load(){},pattern:'Solid',get color(){return '#FFFF00';},set color(v){fills.push([r,c,v]);},clear(){fills.push([r,c,'']);}}}}}
   };
 }};
 const context={sync:async()=>{},workbook:{onSelectionChanged:{add:f=>selectionEvent=f},
 worksheets:{load(){},items:[sheet],getItem:()=>sheet},getSelectedRange:()=>({load(){},worksheet:sheet,
 address:`Sheet1!${selected.row},${selected.column}`,rowIndex:selected.row,columnIndex:selected.column,rowCount:selected.rows,columnCount:selected.columns})}};
 const schema={id:'GROUP',label:'Group',button_text:'Calculate',inputs:[{name:'data',source:'range',type:'matrix',read:['values','format.fillColors'],max_cells:5000}],output:{type:'matrix',destinations:['taskpane','range'],default:'range'}};
 const sandbox={document,Office:{onReady:f=>ready=f,context:{requirements:{isSetSupported:()=>true}}},Excel:{run:fn=>fn(context)},
 Option:function(text,value){this.textContent=text;this.value=value;},fetch:async()=>({ok:true,json:async()=>({version:1,actions:[schema]})}),
 JupyterExcel:{callAction:async(id,args)=>{
   sent=JSON.parse(JSON.stringify(args));
   return {result:{values:[['Yellow',21]],format:{fillColors:[['#FFFF00',null]]}}};
 }}};
 vm.runInNewContext(fs.readFileSync('jupyterexcel/addin_template/actions.js','utf8'),sandbox);
 await ready();assert.equal(elements['action-target-label'].hidden,false,'Starting Cell visible before run');
 const input=elements['action-inputs'].children[0].children[1].children[0];
 input.onclick();await new Promise(setImmediate);
 assert.equal(input.value,'Sheet1!0,0');
 selected={row:2,column:0,rows:2,columns:1};await selectionEvent();assert.equal(input.value,'Sheet1!2,0');
 selected={row:0,column:4,rows:1,columns:1};elements['action-target'].onclick();await new Promise(setImmediate);
 assert.equal(input.value,'Sheet1!2,0','Output selection must preserve input');
 await elements['action-run'].onclick();
 assert.deepEqual(sent,[{values:[[10],[11]],format:{fillColors:[['#FFFF00'],['#FFFF00']]}}]);
 assert.equal(elements['action-write'].disabled,true, 'Automatic write completes without a prompt for empty cells');
 assert.notEqual(elements['action-dialog']?.open,true);
 assert.deepEqual(JSON.parse(JSON.stringify(writes)),[[['Yellow',21]]]);assert.deepEqual(fills,[[0,0,'#FFFF00']]);
 const originalRange = sheet.getRangeByIndexes;
 sheet.getRangeByIndexes = (...args) => {
   const range = originalRange(...args);
   if (args[1] === 4) range.formulas = [['=1+1', 'existing']];
   return range;
 };
 const pendingRun = elements['action-run'].onclick(); await new Promise(setImmediate);
 assert.equal(elements['action-dialog'].open,true);
 const preview=elements['action-dialog-content'].children[2];
 assert.equal(preview.children[1].children[1].textContent,'=1+1');
 elements['action-dialog'].close(); await pendingRun;
 assert.equal(writes.length,1,'Cancel must leave cells untouched');
 const retry=elements['action-write'].onclick();await new Promise(setImmediate);
 elements['action-dialog-content'].children.at(-1).onclick();await retry;
 assert.equal(writes.length,2,'Confirmed overwrite writes once');
 console.log('UI flow passed: mouse input, independent Starting Cell, formatted POST data, preview, confirmed values/fill write.');
})().catch(e=>{console.error(e);process.exitCode=1;});
