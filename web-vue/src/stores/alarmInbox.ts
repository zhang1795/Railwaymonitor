import { reactive } from 'vue'
import { getAlarmNotices, readAlarmNotices, readNoticeIds } from '@/api/alarmNotices'
import type { AlarmNotice } from '@/api/alarmNotices'

export function createAlarmInbox() {
  const state=reactive({ unreadCount:0, items:[] as AlarmNotice[], healthy:false, loading:true, lastSuccess:0, changed:false })
  let generation=0,active=false,pending:Promise<void>|undefined
  let poll:ReturnType<typeof setInterval>|undefined, clock:ReturnType<typeof setInterval>|undefined
  let seen=new Set<string>()
  const refresh=():Promise<void>=>{
    if(!active)return Promise.resolve()
    if(pending)return pending
    const epoch=generation
    pending=(async()=>{
      try {
        const result=await getAlarmNotices()
        if(!active || generation!==epoch)return
        if(state.lastSuccess && (result.unreadCount>state.unreadCount || result.items.some(row=>!seen.has(row.noticeId || row.id))))state.changed=true
        for(const row of result.items)seen.add(row.noticeId || row.id)
        // Only a hint cache; authoritative unread receipts live on the server.
        if(seen.size>2000)seen=new Set(result.items.map(row=>row.noticeId || row.id))
        state.items=result.items;state.unreadCount=result.unreadCount
        state.lastSuccess=Date.now();state.healthy=true
      } catch { if(active && generation===epoch)state.healthy=false }
      finally { if(generation===epoch){state.loading=false;pending=undefined} }
    })()
    return pending
  }
  const stop=()=>{
    active=false;generation++;pending=undefined
    if(poll)clearInterval(poll)
    if(clock)clearInterval(clock)
    poll=undefined;clock=undefined;seen.clear()
    Object.assign(state,{unreadCount:0,items:[],healthy:false,loading:true,lastSuccess:0,changed:false})
    window.removeEventListener('online',refresh)
    document.removeEventListener('visibilitychange',visible)
  }
  const visible=()=>{if(document.visibilityState==='visible')void refresh()}
  const start=()=>{
    if(active)return
    active=true;generation++
    void refresh()
    poll=setInterval(()=>{void refresh()},5000)
    clock=setInterval(()=>{if(Date.now()-state.lastSuccess>15000)state.healthy=false},1000)
    window.addEventListener('online',refresh)
    document.addEventListener('visibilitychange',visible)
  }
  const acknowledge=async(ids:string[],notifications:boolean)=>{
    if(!active)return
    const epoch=generation
    if(notifications)await readNoticeIds(ids)
    else await readAlarmNotices(ids)
    if(!active || epoch!==generation)return
    await pending
    await refresh()
  }
  const markRead=(ids:string[])=>acknowledge(ids,false)
  const markNotificationsRead=(ids:string[])=>acknowledge(ids,true)
  return {state,start,stop,refresh,markRead,markNotificationsRead}
}
export const alarmInbox=createAlarmInbox()
