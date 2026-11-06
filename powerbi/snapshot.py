"""Self-contained PBIP snapshots with no external data-source paths."""
import base64,json,os
import pandas as pd
from . import build_pbip as b
from .to_pbir import report_parts

def build(dataset,output):
    os.makedirs(output,exist_ok=True)
    sm=output+'/UKP.SemanticModel';rp=output+'/UKP.Report'
    td=sm+'/definition/tables';os.makedirs(td,exist_ok=True)
    def write(path,text):
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,'w',encoding='utf-8') as f:f.write(text)
    tables=[];sections=[]
    labels={'dim_sac':'Overview','fact_recon_account':'Reconciliation','fact_pnl':'Financial performance','fact_circuit':'Circuits','fact_voice':'Voice','fact_findings':'Findings','fact_checks':'Data quality','file_status':'File inventory'}
    for filename in sorted(os.listdir(dataset)):
        if not filename.endswith('.csv'):continue
        table=filename[:-4];path=dataset+'/'+filename
        d=pd.read_csv(path,dtype=str,keep_default_na=False)
        if not len(d.columns):continue
        tables.append(table)
        cols=b.col_types(path)
        numeric={'Revenue','Cost','Margin','Costs','Quantity','Rate','SAC Amount','OneBill Amount','Difference','Impact GBP','FY26 YTD Revenue','FY26 YTD Cost','FY26 YTD Margin','FY25 Revenue','FY25 Margin'}
        cols=[(c,'double' if c in numeric else ty) for c,ty in cols]
        rows=[]
        for values in d.itertuples(index=False,name=None):
            rows.append([None if v=='' else int(float(v)) if ty=='int64' else float(v) if ty=='double' else v for v,(_,ty) in zip(values,cols)])
        payload=base64.b64encode(json.dumps(rows,ensure_ascii=False).encode()).decode()
        chunks=', '.join('"'+payload[i:i+16000]+'"' for i in range(0,len(payload),16000))
        types={'string':'type nullable text','double':'type nullable number','int64':'Int64.Type'}
        transforms=', '.join('{'+json.dumps(c)+', '+types[t]+'}' for c,t in cols)
        measure='Records '+table
        lines=[f'table {b.q(table)}',f'\tmeasure {b.q(measure)} = COUNTROWS({b.q(table)})','\t\tformatString: #,##0','']
        if table=='fact_pnl' and 'Margin' in d and len(d):
            current=max(d['FY'])
            periods=sorted(set(d.loc[d['FY']==current,'Period']))
            members=', '.join(json.dumps(v) for v in periods)
            lines += [f"\tmeasure 'Snapshot margin' = IF(SELECTEDVALUE(fact_pnl[Period]) IN {{{members}}}, SUM(fact_pnl[Margin]), BLANK())",'\t\tformatString: #,##0.00','']
        portfolio=[]
        if table=='dim_sac':
            portfolio=[(field,'Snapshot '+field) for field in ['FY26 YTD Revenue','FY26 YTD Margin'] if field in d]
            for field,name in portfolio:lines += [f'\tmeasure {b.q(name)} = SUM(dim_sac[{field}])','\t\tformatString: #,##0.00','']
        for c,t in cols:lines.extend([f'\tcolumn {b.q(c)}',f'\t\tdataType: {t}',f'\t\tsourceColumn: {c}','\t\tsummarizeBy: none',''])
        lines += [f'\tpartition {b.q(table)} = m','\t\tmode: import','\t\tsource =','\t\t\tlet',f'\t\t\t    Rows = Json.Document(Binary.FromText(Text.Combine({{{chunks}}}), BinaryEncoding.Base64)),',f'\t\t\t    Source = Table.FromRows(Rows, {{{', '.join(json.dumps(c) for c,_ in cols)}}}),',f'\t\t\t    Typed = Table.TransformColumnTypes(Source, {{{transforms}}})','\t\t\tin Typed']
        write(td+'/'+table+'.tmdl','\n'.join(lines))
        if table in labels and len(d):
            fields=[('col',c) for c,_ in cols][:12]
            visuals=[b.visual(table+'table','tableEx',240,300,1030,410,labels[table],table,{'Values':fields})]
            if 'SAC' in d:visuals.append(b.visual(table+'slicer','slicer',0,0,220,140,'SAC',table,{'Values':[('col','SAC')]}))
            category=next((c for c in ['Status','Severity','Result','Period','SAC'] if c in d),None)
            if category:
                visuals.append(b.visual(table+'chart','clusteredBarChart',240,0,1030,280,'Records by '+category,table,{'Category':[('col',category)],'Y':[('measure',measure)]}))
            if table=='fact_pnl' and all(c in d for c in ['Period','FY','Margin']):
                visuals=[v for v in visuals if json.loads(v['config'])['name']!=table+'chart']
                visuals.append(b.visual(table+'trend','lineChart',240,0,1030,280,'Comparable-period margin by financial year (GBP)',table,{'Category':[('col','Period')],'Series':[('col','FY')],'Y':[('measure','Snapshot margin')]},('col','Period',1)))
            for i,field in enumerate([c for c in ['Product','Period','Severity','FY'] if c in d][:3]):
                visuals.append(b.visual(table+field+'filter','slicer',0,150+i*170,220,160,field,table,{'Values':[('col',field)]}))
            if portfolio:
                visuals=[v for v in visuals if json.loads(v['config'])['name']!=table+'chart']
                for i,(field,name) in enumerate(portfolio):
                    visuals.append(b.visual(table+'kpi'+str(i),'card',240+i*340,0,330,110,field+' (GBP)',table,{'Values':[('measure',name)]}))
                field,name=portfolio[-1]
                visuals.append(b.visual(table+'portfolio','clusteredBarChart',240,120,1030,170,field+' by SAC (GBP)',table,{'Category':[('col','SAC')],'Y':[('measure',name)]}))
            sections.append({'name':'Page'+str(len(sections)+1),'displayName':labels[table],'width':1280,'height':720,'visualContainers':visuals})
    write(sm+'/definition.pbism',json.dumps({'version':'4.0','settings':{}}))
    write(sm+'/definition/database.tmdl','database\n\tcompatibilityLevel: 1550\n')
    write(sm+'/definition/model.tmdl','model Model\n\tculture: en-GB\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\n'+'\n'.join('ref table '+b.q(t) for t in tables))
    relationships=[]
    for table in tables:
        if table=='dim_sac':continue
        if 'SAC' in pd.read_csv(dataset+'/'+table+'.csv',nrows=0).columns:
            relationships += ['relationship '+b.tag('snapshot',table),f'\tfromColumn: {b.q(table)}.SAC','\ttoColumn: dim_sac.SAC','']
    write(sm+'/definition/relationships.tmdl','\n'.join(relationships))
    for path,text in report_parts(sections,model_folder='../UKP.SemanticModel').items():write(rp+'/'+path,text)
    write(output+'/UKP.pbip',json.dumps({'version':'1.0','artifacts':[{'report':{'path':'UKP.Report'}}],'settings':{'enableAutoRecovery':True}}))
    write(output+'/README.txt','Open UKP.pbip in Power BI Desktop. This is a self-contained data snapshot. Refresh loads the embedded snapshot, not new source files. Rerun the website for updated results. Desktop compatibility still requires native validation.')
