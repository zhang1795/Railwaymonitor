const test=require('node:test'),assert=require('node:assert/strict')
const echarts=require('echarts')
const {fixture,flush}=require('./frontend-fixture.cjs')
const stats=trendData=>({trendData,typeDistribution:[],locationHeatmap:[],typeNameDistribution:[],totalCount:0,processingCount:0,handledCount:0,pendingCount:0})
const stamp=date=>Date.parse(date+'T00:00:00Z')
function page(getData=async()=>stats([])) {
  const charts=[]
  const f=fixture({modules:{echarts:{...echarts,init:()=>{
    const chart=echarts.init(null,null,{renderer:'svg',ssr:true,width:1200,height:400})
    charts.push(chart);return chart
  }},'@/api/statistics':{getAbnormalEventStatistics:getData}}})
  const p=f.component('views/statistics/AbnormalEvent.vue',['trendChart','levelChart','locationChart','typeChart','initTrendChart','initCharts'])
  for(const name of ['trendChart','levelChart','locationChart','typeChart'])p[name].value={}
  return {f,p,charts}
}

test('screenshot dates retain their counts in chronological order and calendar spacing',()=>{
  const rows=[
    {date:'2025-12-14',count:1},{date:'2025-11-24',count:2},{date:'2025-11-23',count:3},
    {date:'2026-11-11',count:115},{date:'2026-11-10',count:950},{date:'2025-12-09',count:4},
    {date:'2026-09-14',count:10},{date:'2026-08-03',count:12},{date:'2025-11-18',count:5},
  ]
  const original=JSON.stringify(rows),{f,p,charts}=page()
  p.initTrendChart(stats(rows));const chart=charts[0],option=chart.getOption(),points=option.series[0].data
  assert.equal(option.xAxis[0].type,'time');assert.equal(option.useUTC,true)
  assert.equal(option.xAxis[0].axisPointer.label.formatter({value:stamp('2026-11-11')}),'2026-11-11')
  assert.equal(option.dataZoom.length,2)
  assert(points.every((point,index)=>!index || point[0]>points[index-1][0]))
  const values=new Map(points)
  for(const row of rows)assert.equal(values.get(stamp(row.date)),row.count)
  assert.equal(JSON.stringify(rows),original,'sorting must not reorder the shared response')
  const x=date=>chart.convertToPixel({xAxisIndex:0},stamp(date))
  assert(x('2026-11-10')<x('2026-11-11'))
  const oneDay=x('2026-11-11')-x('2026-11-10')
  const tenDays=x('2026-11-10')-x('2026-10-31')
  assert(Math.abs(tenDays/oneDay-10)<1e-6,'calendar gaps must not be compressed into category slots')
  assert.match(chart.renderToSVGString(),/异常趋势分析/)
  f.unmount()
})

test('missing daily counts become zero across leap days and long gaps without a huge allocation',()=>{
  const {f,p,charts}=page()
  p.initTrendChart(stats([{date:'2024-03-01',count:8},{date:'2024-02-28',count:4},{date:'2044-01-01',count:2}]))
  const points=charts[0].getOption().series[0].data,values=new Map(points)
  assert.equal(values.get(stamp('2024-02-29')),0)
  assert.equal(values.get(stamp('2024-03-02')),0)
  assert.equal(values.get(stamp('2043-12-31')),0)
  assert.equal(points.length,6)
  assert.equal(charts[0].getOption().series[0].smooth,false)
  f.unmount()
})

test('refresh reuses charts and replaces old dates for single-day and empty responses',async()=>{
  let data=stats([{date:'2026-01-01',count:4},{date:'2026-01-02',count:7}])
  const {f,p,charts}=page(async()=>data)
  await p.initCharts();assert.equal(charts.length,4)
  data=stats([{date:'2026-11-11',count:3}]);await p.initCharts()
  assert.equal(charts.length,4)
  assert.deepEqual(charts[3].getOption().series[0].data,[[stamp('2026-11-11'),3]])
  data=stats([]);await p.initCharts()
  assert.deepEqual(charts[3].getOption().series[0].data,[])
  f.unmount();assert(charts.every(chart=>chart.isDisposed()))
})

test('duplicate refreshes are serialized and late responses cannot create charts after leaving',async()=>{
  let resolve,calls=0
  const {f,p,charts}=page(()=>{calls++;return new Promise(done=>resolve=done)})
  const first=p.initCharts();await p.initCharts();assert.equal(calls,1)
  f.unmount();resolve(stats([{date:'2026-11-11',count:8}]))
  await first;await flush();assert.equal(charts.length,0)
})
