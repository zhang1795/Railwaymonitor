package com.example;

import com.example.detection.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @AutoConfigureMockMvc @ActiveProfiles("test")
@org.springframework.context.annotation.Import(ManualEventRace.class)
class P0IntegrationTest {
    private static final String evidenceRoot=java.nio.file.Path.of(System.getProperty("java.io.tmpdir"),"railway-p1-evidence-"+UUID.randomUUID()).toString();
    private static final String recordingRoot=java.nio.file.Path.of(System.getProperty("java.io.tmpdir"),"railway-p1-recordings-"+UUID.randomUUID()).toString();
    @DynamicPropertySource static void database(DynamicPropertyRegistry properties){
        properties.add("railway.evidence-root",()->evidenceRoot);properties.add("railway.recording-root",()->recordingRoot);
        String url=System.getenv("P0_TEST_DB_URL");
        if(url!=null){
            if(!url.startsWith("jdbc:mysql://127.0.0.1:13317/railway_p0_test?"))throw new IllegalArgumentException("P0 tests only allow the disposable 13317/railway_p0_test database");
            properties.add("spring.datasource.url",()->url);properties.add("spring.datasource.driver-class-name",()->"com.mysql.cj.jdbc.Driver");properties.add("spring.datasource.username",()->"root");
        }
    }
    @Autowired org.springframework.context.ApplicationContext application;
    @Autowired JdbcTemplate jdbc;
    @Autowired DetectionIngestService ingest;
    @Autowired MonitoringService monitoring;
    @Autowired ObjectMapper json;
    @Autowired MockMvc mvc;
    @Autowired PasswordEncoder passwords;
    @Autowired com.example.service.CameraService cameras;
    @Autowired com.example.service.UserService accounts;
    @Autowired com.example.service.AbnormalEventService alarms;
    String session;
    Instant observedAt;
    static String encoded;
    final String rawPassword="correct-test-password-2026";
    @BeforeEach void fixture(){
        for(String table:List.of("notification_delivery","recording_analysis","recording_clip","monitoring_fault_receipt","monitoring_fault","monitoring_health_sample","monitoring_metric","alarm_edit_version","worker_evidence_status","alarm_evidence","alarm_notice_receipt","alarm_notice","alarm_handling_audit","alarm_transition","alarm_source_link","risk_incident","risk_track","session_risk_policy","camera_risk_revision","camera_risk_rule","alarm_notice_read","preview_grant","detection_track","detection_rejection","detection_receipt","monitoring_task","monitoring_session","abnormal_event","camera","user"))jdbc.update("DELETE FROM `"+table+"`");
        var transport=application.getBean(NotificationTransport.class);
        for(String name:List.of("webhookUrl","webhookKey","accessKey","secret","sign","template","recipients"))org.springframework.test.util.ReflectionTestUtils.setField(transport,name,"");
        org.springframework.test.util.ReflectionTestUtils.setField(transport,"loopback",false);
        if(encoded==null)encoded=passwords.encode(rawPassword);
        jdbc.update("INSERT INTO `user`(id,username,password,role,status,security_version,password_change_required) VALUES(1,'admin',?,1,1,0,FALSE),(2,'operator',?,0,1,0,FALSE)",encoded,encoded);
        jdbc.update("INSERT INTO camera(id,name,location,rtsp_url,status) VALUES(1,'test','test-location','rtsp://127.0.0.1:8554/test',1)");
        session=(String)monitoring.setEnabled(1,true).get("session_id");
        observedAt=Instant.now().minusSeconds(2);
    }
    ObjectNode event(long sequence,int cls,double score,String state){
        var e=json.createObjectNode();e.put("protocolVersion",3);e.put("workerId","detector-1");e.put("eventId",UUID.randomUUID().toString().replace("-",""));
        e.put("cameraId","1");e.put("sessionId",session);e.put("trackId","1");e.put("generation",1);e.put("sequence",sequence);e.put("state",state);
        e.put("firstSeen",observedAt.toString());e.put("lastSeen",observedAt.plusSeconds(1).toString());e.put("processedAt",Instant.now().toString());e.put("timeSource","received_at");
        e.put("classId",cls);e.put("className",DetectionIngestService.NAMES.get(cls));e.put("confidence",score);e.put("frameWidth",640);e.put("frameHeight",480);
        e.putArray("bbox").add(10).add(20).add(100).add(120);
        var evidence=e.putObject("classEvidence");evidence.putObject(String.valueOf(cls)).put("count",sequence).put("maxScore",score);return e;
    }
    Map<String,Object> receive(ObjectNode e){return ingest.receive("detector-1",e.toString());}
    @Test void duplicateMessagesAndTwoConsumersCreateOneAlarm()throws Exception{
        var e=event(1,12,.8,"ACTIVE");String payload=e.toString();
        var pool=Executors.newFixedThreadPool(4);
        try{
            var calls=new ArrayList<Callable<Map<String,Object>>>();for(int i=0;i<8;i++)calls.add(()->ingest.receive("detector-1",payload));
            for(var result:pool.invokeAll(calls))assertEquals("APPLIED",result.get().get("status"));
        }finally{pool.shutdownNow();}
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM detection_receipt",Integer.class));
    }
    @Test void categoryConfidenceCorrectsWithoutOverwritingHumanResolution(){
        assertEquals("APPLIED",receive(event(1,12,.3,"ACTIVE")).get("status"));
        jdbc.update("UPDATE abnormal_event SET status=2,handler_id=2,handle_result='resolved'");
        var next=event(2,2,.95,"ACTIVE");next.with("classEvidence").putObject("12").put("count",1).put("maxScore",.3);
        assertEquals("APPLIED",receive(next).get("status"));
        var row=jdbc.queryForMap("SELECT * FROM abnormal_event");
        assertEquals("牛",row.get("type"));assertEquals(.95,((Number)row.get("confidence")).doubleValue());
        assertEquals(2,((Number)row.get("status")).intValue());assertEquals("resolved",row.get("handle_result"));
    }
    @Test void manualCategoryIsPreservedSeparatelyFromDetectedCategory(){
        receive(event(1,12,.3,"ACTIVE"));jdbc.update("UPDATE abnormal_event SET manual_override=TRUE,type='人工核验'");
        var next=event(2,2,.95,"ENDED");next.with("classEvidence").putObject("12").put("count",1).put("maxScore",.3);receive(next);
        var row=jdbc.queryForMap("SELECT * FROM abnormal_event");assertEquals("人工核验",row.get("type"));assertEquals("牛",row.get("detected_type"));
    }
    @Test void finalSnapshotCanArriveFirstAndLateStartCannotReopen(){
        receive(event(2,12,.8,"ENDED"));receive(event(1,12,.8,"ACTIVE"));
        assertEquals("ENDED",jdbc.queryForObject("SELECT detection_state FROM abnormal_event",String.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void invalidScoreTimezoneSessionAndClassAreQuarantined(){
        var bad=event(1,12,.8,"ACTIVE");bad.putNull("confidence");assertEquals("REJECTED",receive(bad).get("status"));
        bad=event(1,12,.8,"ACTIVE");bad.put("firstSeen","2026-01-01T01:00:00");assertEquals("REJECTED",receive(bad).get("status"));
        bad=event(1,12,.8,"ACTIVE");bad.put("sessionId","0".repeat(32));assertEquals("REJECTED",receive(bad).get("status"));
        bad=event(1,12,.8,"ACTIVE");bad.put("className","cow");assertEquals("REJECTED",receive(bad).get("status"));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(4,jdbc.queryForObject("SELECT COUNT(*) FROM detection_rejection",Integer.class));
    }
    @Test void sameIdDifferentBodyIsNotAcknowledgedAsDuplicateSuccess(){
        var e=event(1,12,.8,"ACTIVE");receive(e);e.put("confidence",.7);
        assertEquals("REJECTED",receive(e).get("status"));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void transactionFailureRollsBackAlarmAndReplaySucceeds(){
        var e=event(1,12,.8,"ACTIVE");String id=e.path("eventId").asText();
        jdbc.execute("ALTER TABLE detection_receipt ADD COLUMN injected_failure INTEGER DEFAULT 0");
        try{assertThrows(org.springframework.dao.DataAccessException.class,()->receive(e));
            assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
            assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM detection_track",Integer.class));
        }finally{jdbc.execute("ALTER TABLE detection_receipt DROP COLUMN injected_failure");}
        assertEquals("APPLIED",receive(e).get("status"));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void backgroundCommandsExistWithoutAnyBrowserAndDisableIsFenced(){
        var command=monitoring.commands().get(0);assertEquals(true,command.get("enabled"));assertEquals(session,command.get("sessionId"));
        monitoring.setEnabled(1,false);var stopped=monitoring.commands().get(0);
        assertEquals(false,stopped.get("enabled"));assertTrue(((Number)stopped.get("generation")).longValue()>((Number)command.get("generation")).longValue());
        var status=json.createObjectNode().put("sessionId",session).put("state","RUNNING").put("revision",99);
        monitoring.status("detector-1",status);assertNotEquals("RUNNING",monitoring.list().get(0).get("state"));
    }
    @Test void lateEventsFromInterruptedSessionRemainInterrupted(){
        monitoring.setEnabled(1,false);assertEquals("APPLIED",receive(event(1,12,.8,"ACTIVE")).get("status"));
        assertEquals("INTERRUPTED",jdbc.queryForObject("SELECT detection_state FROM abnormal_event",String.class));
    }
    @Test void workerProcessLossRequestsNewSessionEvenWithLowerLocalRevision(){
        monitoring.status("detector-1",json.createObjectNode().put("sessionId",session).put("state","RUNNING").put("revision",100));
        monitoring.status("detector-1",json.createObjectNode().put("sessionId",session).put("state","FAILED").put("lostSession",true).put("revision",0));
        assertNotEquals(session,monitoring.commands().get(0).get("sessionId"));
    }
    @Test void retiredCameraPreservesDelayedEventsButCannotBeStarted(){
        assertThrows(com.example.common.exception.BusinessException.class,()->cameras.deleteCamera(1L));
        monitoring.setEnabled(1,false);cameras.deleteCamera(1L);
        assertNull(cameras.getById(1L));
        assertThrows(com.example.common.exception.BusinessException.class,()->monitoring.setEnabled(1,true));
        assertEquals("APPLIED",receive(event(1,12,.8,"ACTIVE")).get("status"));
        assertEquals("INTERRUPTED",jdbc.queryForObject("SELECT detection_state FROM abnormal_event",String.class));
    }
    @Test void enabledCameraSourceCannotChangeInTheSameSession(){
        var update=new com.example.dto.camera.CameraUpdateDTO();
        update.setId(1L);update.setName("test");update.setLocation("test-location");
        update.setRtspUrl("rtsp://127.0.0.1:8554/changed");
        assertThrows(com.example.common.exception.BusinessException.class,()->cameras.updateCamera(update));
        monitoring.setEnabled(1,false);cameras.updateCamera(update);
        assertEquals(update.getRtspUrl(),jdbc.queryForObject("SELECT rtsp_url FROM camera WHERE id=1",String.class));
    }
    private MockHttpSession login(String username)throws Exception{
        var token=mvc.perform(get("/auth/csrf").servletPath("/auth/csrf")).andExpect(status().isOk()).andReturn();
        var session=(MockHttpSession)token.getRequest().getSession();var data=json.readTree(token.getResponse().getContentAsString()).path("data");
        mvc.perform(post("/user/login").servletPath("/user/login").session(session).header(data.path("headerName").asText(),data.path("token").asText())
            .contentType("application/json").content(json.writeValueAsString(Map.of("username",username,"password",rawPassword))))
            .andExpect(status().isOk());return session;
    }
    private MockHttpServletRequestBuilder csrf(MockHttpServletRequestBuilder request,MockHttpSession session)throws Exception{
        var token=mvc.perform(get("/auth/csrf").servletPath("/auth/csrf").session(session)).andReturn();
        var data=json.readTree(token.getResponse().getContentAsString()).path("data");
        return request.session(session).header(data.path("headerName").asText(),data.path("token").asText());
    }
    @Test void unauthenticatedApiIsDeniedAndLoginPersistsAcrossRequests()throws Exception{
        mvc.perform(get("/monitoring").servletPath("/monitoring")).andExpect(status().isUnauthorized());
        var session=login("operator");mvc.perform(get("/monitoring").servletPath("/monitoring").session(session)).andExpect(status().isOk());
    }
    @Test void ordinaryUserCannotManageAccountsOrMonitoring()throws Exception{
        var s=login("operator");mvc.perform(get("/user/page").servletPath("/user/page").session(s)).andExpect(status().isForbidden());
        mvc.perform(csrf(put("/monitoring/1").servletPath("/monitoring/1"),s).contentType("application/json").content("{\"enabled\":false}")).andExpect(status().isForbidden());
        mvc.perform(csrf(put("/user").servletPath("/user"),s).contentType("application/json").content("{\"id\":2,\"role\":1}")).andExpect(status().isForbidden());
    }
    @Test void csrfRequiredAndNoPasswordHashOrRtspCredentialIsReturned()throws Exception{
        var s=login("admin");mvc.perform(put("/monitoring/1").servletPath("/monitoring/1").session(s).contentType("application/json").content("{\"enabled\":false}")).andExpect(status().isForbidden());
        String users=mvc.perform(get("/user/page").servletPath("/user/page").session(s)).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertFalse(users.contains("\"password\":"));assertFalse(users.contains("$2"));
        String cameras=mvc.perform(get("/camera/page").servletPath("/camera/page").session(s)).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertFalse(cameras.contains("rtsp://"));
    }
    @Test void disabledUserAndPreviewGrantCannotContinue()throws Exception{
        var s=login("operator");var created=mvc.perform(csrf(post("/preview/grant").servletPath("/preview/grant"),s)).andExpect(status().isOk()).andReturn();
        String grant=json.readTree(created.getResponse().getContentAsString()).path("data").path("grant").asText();
        jdbc.update("UPDATE `user` SET status=0,security_version=1 WHERE id=2");
        mvc.perform(get("/monitoring").servletPath("/monitoring").session(s)).andExpect(status().isUnauthorized());
        mvc.perform(post("/_internal/preview/resolve").servletPath("/_internal/preview/resolve").header("Authorization","Bearer isolated-test-service-key-32-characters-long")
            .contentType("application/json").content(json.writeValueAsString(Map.of("grant",grant,"cameraId",1)))).andExpect(status().isUnauthorized());
    }
    @Test void concurrentPasswordResetsRevokeOldSessionAndDoNotReuseSecurityVersion()throws Exception{
        var s=login("operator");var pool=Executors.newFixedThreadPool(2);
        try{
            var results=pool.invokeAll(List.<Callable<String>>of(()->accounts.resetPassword(2L),()->accounts.resetPassword(2L)));
            assertNotEquals(results.get(0).get(),results.get(1).get());
        }finally{pool.shutdownNow();}
        assertEquals(2,jdbc.queryForObject("SELECT security_version FROM `user` WHERE id=2",Long.class));
        mvc.perform(get("/monitoring").servletPath("/monitoring").session(s)).andExpect(status().isUnauthorized());
    }
    @Test void previewServiceNeedsSecretAndUnknownCameraIsRejected()throws Exception{
        mvc.perform(post("/_internal/preview/resolve").servletPath("/_internal/preview/resolve").contentType("application/json").content("{}")).andExpect(status().isUnauthorized());
    }
    @Test void validPreviewGrantResolvesServerSourceAndRenews()throws Exception{
        var s=login("operator");
        var created=mvc.perform(csrf(post("/preview/grant").servletPath("/preview/grant"),s)).andExpect(status().isOk()).andReturn();
        String grant=json.readTree(created.getResponse().getContentAsString()).path("data").path("grant").asText();
        mvc.perform(post("/_internal/preview/resolve").servletPath("/_internal/preview/resolve").header("Authorization","Bearer isolated-test-service-key-32-characters-long")
            .contentType("application/json").content(json.writeValueAsString(Map.of("grant",grant,"cameraId",1))))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.videoUrl").value("rtsp://127.0.0.1:8554/test"));
        mvc.perform(csrf(post("/preview/grant/renew").servletPath("/preview/grant/renew"),s).contentType("application/json").content(json.writeValueAsString(Map.of("grant",grant)))).andExpect(status().isOk());
    }
    @Test void cameraWriteIsAdminOnlyAndHandlerIdentityCannotBeForged()throws Exception{
        var s=login("operator");
        mvc.perform(csrf(put("/camera").servletPath("/camera"),s).contentType("application/json").content("{\"id\":1,\"name\":\"hijack\",\"location\":\"x\"}")).andExpect(status().isForbidden());
        receive(event(1,12,.8,"ACTIVE"));long alarm=jdbc.queryForObject("SELECT id FROM abnormal_event",Long.class);
        mvc.perform(csrf(post("/Abnormal-event/"+alarm+"/handle").servletPath("/Abnormal-event/"+alarm+"/handle"),s)
            .contentType("application/json").content("{\"id\":"+alarm+",\"handlerId\":1,\"version\":0,\"handleResult\":\"checked\"}")).andExpect(status().isOk());
        assertEquals(2,jdbc.queryForObject("SELECT handler_id FROM abnormal_event",Long.class));
    }
    @Test void legacyLoginUpgradesHashAndRequiresPasswordChange()throws Exception{
        jdbc.update("UPDATE `user` SET password=? WHERE id=2",cn.hutool.crypto.SecureUtil.md5(rawPassword));
        var s=login("operator");
        assertTrue(jdbc.queryForObject("SELECT password FROM `user` WHERE id=2",String.class).startsWith("$2"));
        mvc.perform(get("/monitoring").servletPath("/monitoring").session(s)).andExpect(status().isForbidden());
        mvc.perform(get("/user/current").servletPath("/user/current").session(s)).andExpect(status().isOk());
    }

    static java.util.stream.Stream<org.junit.jupiter.params.provider.Arguments> invalidSnapshotCases(){
        var cases=new LinkedHashMap<String,java.util.function.Consumer<ObjectNode>>();
        cases.put("NaN confidence",e->e.put("confidence",Double.NaN));
        cases.put("confidence above one",e->e.put("confidence",1.01));
        cases.put("unsupported class",e->e.put("classId",13));
        cases.put("negative bbox",e->e.putArray("bbox").add(-1).add(20).add(100).add(120));
        cases.put("reversed bbox",e->e.putArray("bbox").add(100).add(20).add(10).add(120));
        cases.put("bbox beyond frame",e->e.putArray("bbox").add(10).add(20).add(641).add(120));
        cases.put("zero frame height",e->e.put("frameHeight",0));
        cases.put("sequence overflow",e->e.put("sequence",new java.math.BigInteger("9223372036854775808")));
        cases.put("zero evidence count",e->((ObjectNode)e.path("classEvidence").path("12")).put("count",0));
        cases.put("fractional evidence count",e->((ObjectNode)e.path("classEvidence").path("12")).put("count",1.5));
        cases.put("inconsistent class maximum",e->((ObjectNode)e.path("classEvidence").path("12")).put("maxScore",.1));
        cases.put("unknown evidence class",e->((ObjectNode)e.path("classEvidence")).putObject("13").put("count",1).put("maxScore",.8));
        cases.put("timestamp below SQL range",e->e.put("firstSeen","0001-01-01T00:00:00Z"));
        cases.put("timezone conversion below SQL range",e->e.put("firstSeen","1000-01-01T00:00:00+14:00"));
        return cases.entrySet().stream().map(e->org.junit.jupiter.params.provider.Arguments.of(e.getKey(),e.getValue()));
    }
    @org.junit.jupiter.params.ParameterizedTest(name="{0}")
    @org.junit.jupiter.params.provider.MethodSource("invalidSnapshotCases")
    void malformedSnapshotsAreDurablyRejected(String name,java.util.function.Consumer<ObjectNode> mutate){
        var e=event(1,12,.8,"ACTIVE");mutate.accept(e);
        assertEquals("REJECTED",receive(e).get("status"),name);
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM detection_rejection",Integer.class));
    }
    @Test void lostApplicationAckReplaysCommittedDataWithoutDuplicateAlarm(){
        var e=event(1,12,.8,"ACTIVE");receive(e); // Intentionally discard its business ACK.
        var response=receive(e);
        assertEquals("APPLIED",response.get("status"));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM detection_receipt",Integer.class));
    }
    @Test void regressedEvidenceAndReusedSequenceCannotDamageAcceptedSnapshot(){
        receive(event(2,12,.8,"ACTIVE"));
        assertEquals("REJECTED",receive(event(2,12,.8,"ENDED")).get("status"));
        assertEquals("REJECTED",receive(event(3,12,.7,"ENDED")).get("status"));
        assertEquals("ACTIVE",jdbc.queryForObject("SELECT detection_state FROM abnormal_event",String.class));
        assertEquals(2,jdbc.queryForObject("SELECT sequence_no FROM detection_track",Long.class));
    }
    @Test void reusedTrackIdInNewSessionCreatesSeparateBusinessIdentity(){
        receive(event(1,12,.8,"ACTIVE"));monitoring.setEnabled(1,false);
        var next=monitoring.setEnabled(1,true);session=(String)next.get("session_id");
        var e=event(1,2,.9,"ACTIVE");e.put("generation",((Number)next.get("generation")).longValue());
        assertEquals("APPLIED",receive(e).get("status"));
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event WHERE detection_state='INTERRUPTED'",Integer.class));
    }
    @Test void knownSessionCannotBeReboundToAnotherCamera(){
        var e=event(1,12,.8,"ACTIVE");e.put("cameraId","2");
        assertEquals("REJECTED",receive(e).get("status"));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void expiredPreviewAndAnotherSessionCannotRenewGrant()throws Exception{
        var a=login("operator");var b=login("operator");
        var created=mvc.perform(csrf(post("/preview/grant").servletPath("/preview/grant"),a)).andReturn();
        String grant=json.readTree(created.getResponse().getContentAsString()).path("data").path("grant").asText();
        mvc.perform(csrf(post("/preview/grant/renew").servletPath("/preview/grant/renew"),b).contentType("application/json").content(json.writeValueAsString(Map.of("grant",grant)))).andExpect(status().isUnauthorized());
        jdbc.update("UPDATE preview_grant SET expires_at=?",DetectionIngestService.utc(Instant.now().minusSeconds(1)));
        mvc.perform(csrf(post("/preview/grant/renew").servletPath("/preview/grant/renew"),a).contentType("application/json").content(json.writeValueAsString(Map.of("grant",grant)))).andExpect(status().isUnauthorized());
        mvc.perform(post("/_internal/preview/resolve").servletPath("/_internal/preview/resolve").header("Authorization","Bearer isolated-test-service-key-32-characters-long")
            .contentType("application/json").content(json.writeValueAsString(Map.of("grant",grant,"cameraId",1)))).andExpect(status().isUnauthorized());
    }
    @Test void validServiceSecretCannotBeUsedFromBrowserOrigin()throws Exception{
        mvc.perform(post("/_internal/preview/resolve").servletPath("/_internal/preview/resolve").header("Origin","https://attacker.invalid")
            .header("Authorization","Bearer isolated-test-service-key-32-characters-long").contentType("application/json").content("{}"))
            .andExpect(status().isUnauthorized());
    }
    @Test void roleChangeRevokesExistingSessionAndNewLoginLoadsNewRole()throws Exception{
        var admin=login("admin");var previous=login("operator");
        mvc.perform(csrf(put("/user").servletPath("/user"),admin).contentType("application/json").content("{\"id\":2,\"role\":1}")).andExpect(status().isOk());
        mvc.perform(get("/monitoring").servletPath("/monitoring").session(previous)).andExpect(status().isUnauthorized());
        var current=login("operator");mvc.perform(get("/user/page").servletPath("/user/page").session(current)).andExpect(status().isOk());
    }
    @Test void ordinaryUserCannotDeleteOrResetAccountsOrDeleteCameras()throws Exception{
        var s=login("operator");
        mvc.perform(csrf(delete("/user/1").servletPath("/user/1"),s)).andExpect(status().isForbidden());
        mvc.perform(csrf(put("/user/1/reset-password").servletPath("/user/1/reset-password"),s)).andExpect(status().isForbidden());
        mvc.perform(csrf(delete("/camera/1").servletPath("/camera/1"),s)).andExpect(status().isForbidden());
    }
    @org.junit.jupiter.params.ParameterizedTest(name="manual {0} concurrent with final detection")
    @org.junit.jupiter.params.provider.ValueSource(strings={"handle","edit","status"})
    void manualChangesCannotRestoreStaleAutomaticDetectionFields(String operation)throws Exception{
        receive(event(1,12,.3,"ACTIVE"));long id=jdbc.queryForObject("SELECT id FROM abnormal_event",Long.class);
        var plan=ManualEventRace.arm();
        var pool=Executors.newSingleThreadExecutor(r->new Thread(r,"p0-manual-race"));
        try{
            var manual=pool.submit(()->{
                var context=org.springframework.security.core.context.SecurityContextHolder.createEmptyContext();
                context.setAuthentication(new org.springframework.security.authentication.UsernamePasswordAuthenticationToken(
                    new com.example.security.SessionUser(1,0),null,List.of(new org.springframework.security.core.authority.SimpleGrantedAuthority("ROLE_ADMIN"))));
                org.springframework.security.core.context.SecurityContextHolder.setContext(context);
                try{
                    if("handle".equals(operation)){
                        var dto=new com.example.dto.Abnormal.AbnormalEventHandleDTO();dto.setId(id);dto.setHandlerId(2L);dto.setVersion(0L);dto.setHandleResult("checked");alarms.handleAbnormalEvent(dto);
                    }else if("edit".equals(operation)){
                        var dto=new com.example.dto.Abnormal.AbnormalEventUpdateDTO();dto.setId(id);dto.setVersion(0L);dto.setType("工人");dto.setDescription("人工核验");alarms.updateAbnormalEvent(dto);
                    }else alarms.updateAbnormalEventStatus(id,2,0L,"checked");
                }finally{org.springframework.security.core.context.SecurityContextHolder.clearContext();}
            });
            boolean scheduled=plan.read.await(5,TimeUnit.SECONDS);
            if(!scheduled && manual.isDone())manual.get();
            assertTrue(scheduled,"manual snapshot read scheduling hook was not reached");
            var next=event(2,2,.95,"ENDED");next.put("lastSeen",observedAt.plusSeconds(2).toString());
            next.with("classEvidence").putObject("12").put("count",1).put("maxScore",.3);
            assertEquals("APPLIED",receive(next).get("status"));
            plan.resume.countDown();manual.get(5,TimeUnit.SECONDS);
            var row=jdbc.queryForMap("SELECT * FROM abnormal_event");
            assertEquals("ENDED",row.get("detection_state"),operation+" restored a stale automatic state");
            assertEquals("牛",row.get("detected_type"));assertEquals(.95,((Number)row.get("confidence")).doubleValue(),1e-9);
            if("edit".equals(operation))assertEquals("工人",row.get("type"));
            else assertEquals(2,((Number)row.get("status")).intValue());
        }finally{plan.resume.countDown();pool.shutdownNow();ManualEventRace.clear();}
    }
    @Test void concurrentShuffledSnapshotsAndRetriesConvergeToSingleFinalAlarm()throws Exception{
        var messages=new ArrayList<String>();
        for(int i=1;i<=50;i++){
            String payload=event(i,12,.2+.6*i/50,i==50?"ENDED":"ACTIVE").toString();messages.add(payload);messages.add(payload);
        }
        Collections.shuffle(messages,new Random(17));var pool=Executors.newFixedThreadPool(8);
        try{
            var calls=messages.stream().<Callable<Map<String,Object>>>map(body->()->ingest.receive("detector-1",body)).toList();
            for(var future:pool.invokeAll(calls))assertEquals("APPLIED",future.get().get("status"));
        }finally{pool.shutdownNow();}
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(50,jdbc.queryForObject("SELECT COUNT(*) FROM detection_receipt",Integer.class));
        assertEquals(50,jdbc.queryForObject("SELECT sequence_no FROM detection_track",Long.class));
        assertEquals("ENDED",jdbc.queryForObject("SELECT detection_state FROM abnormal_event",String.class));
    }
    @Test void liveObservationBeforeSessionWindowIsQuarantined(){
        var e=event(1,12,.8,"ACTIVE");e.put("firstSeen",observedAt.minusSeconds(3600).toString());
        assertEquals("REJECTED",receive(e).get("status"));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void liveObservationBeyondEndedSessionWindowIsQuarantined(){
        monitoring.setEnabled(1,false);var e=event(1,12,.8,"ENDED");
        e.put("lastSeen",Instant.now().plusSeconds(90).toString());e.put("processedAt",Instant.now().plusSeconds(45).toString());
        assertEquals("REJECTED",receive(e).get("status"));
    }
    @Test void historicalMediaTimeIsNotConfusedWithLiveSessionClock(){
        var e=event(1,12,.8,"ENDED");e.put("timeSource","media_time");
        e.put("firstSeen","2026-01-01T01:00:00Z");e.put("lastSeen","2026-01-01T01:00:01Z");
        assertEquals("APPLIED",receive(e).get("status"));
    }
    private com.fasterxml.jackson.databind.JsonNode notices(MockHttpSession s,String query)throws Exception{
        return json.readTree(mvc.perform(get("/alarm-notices"+query).servletPath("/alarm-notices").session(s))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data");
    }
    private void readNotices(MockHttpSession s,List<Long> ids)throws Exception{
        mvc.perform(csrf(post("/alarm-notices/read").servletPath("/alarm-notices/read"),s)
            .contentType("application/json").content(json.writeValueAsString(Map.of("ids",ids)))).andExpect(status().isOk());
    }
    @Test void noticeReadIsPerAccountPersistentAndDoesNotResolveAlarm()throws Exception{
        receive(event(1,12,.8,"ACTIVE"));long id=jdbc.queryForObject("SELECT id FROM abnormal_event",Long.class);
        var operator=login("operator");var admin=login("admin");
        assertEquals(1,notices(operator,"").path("unreadCount").asInt());
        readNotices(operator,List.of(id,id));readNotices(operator,List.of(id));
        assertEquals(0,notices(login("operator"),"").path("unreadCount").asInt());
        assertEquals(1,notices(admin,"").path("unreadCount").asInt());
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_notice_read",Integer.class));
        assertEquals(0,jdbc.queryForObject("SELECT status FROM abnormal_event",Integer.class));
        assertEquals("ACTIVE",jdbc.queryForObject("SELECT detection_state FROM abnormal_event",String.class));
    }
    @Test void noticePaginationIsStableAcrossBackdatedAndNewArrivals()throws Exception{
        for(long id=901;id<=925;id++){jdbc.update("INSERT INTO abnormal_event(id,camera_id,event_time,location,level,status) VALUES(?,1,'2020-01-01','test',1,0)",id);jdbc.update("INSERT INTO alarm_notice(alarm_id,kind,bucket,created_at) VALUES(?,'FIRST',0,CURRENT_TIMESTAMP)",id);}
        var operator=login("operator");var first=notices(operator,"?size=10");
        assertEquals(25,first.path("unreadCount").asInt());assertEquals("925",first.path("items").get(0).path("id").asText());
        jdbc.update("INSERT INTO abnormal_event(id,camera_id,event_time,location,level,status) VALUES(926,1,'2000-01-01','test',1,0)");
        jdbc.update("INSERT INTO alarm_notice(alarm_id,kind,bucket,created_at) VALUES(926,'FIRST',0,CURRENT_TIMESTAMP)");
        var second=notices(operator,"?size=10&beforeId="+first.path("nextBeforeId").asText());
        assertEquals("915",second.path("items").get(0).path("id").asText());
        assertEquals("926",notices(operator,"").path("items").get(0).path("id").asText());
    }
    @Test void lateCommittingLowerIdRemainsUnreadAfterHigherIdWasRead()throws Exception{
        var operator=login("operator");
        try(var delayed=jdbc.getDataSource().getConnection()){
            delayed.setAutoCommit(false);
            try(var statement=delayed.prepareStatement("INSERT INTO abnormal_event(id,camera_id,event_time,location,level,status) VALUES(901,1,'2020-01-01','test',1,0)")){statement.executeUpdate();}
            try(var statement=delayed.prepareStatement("INSERT INTO alarm_notice(alarm_id,kind,bucket,created_at) VALUES(901,'FIRST',0,CURRENT_TIMESTAMP)")){statement.executeUpdate();}
            jdbc.update("INSERT INTO abnormal_event(id,camera_id,event_time,location,level,status) VALUES(902,1,'2020-01-01','test',1,0)");
            jdbc.update("INSERT INTO alarm_notice(alarm_id,kind,bucket,created_at) VALUES(902,'FIRST',0,CURRENT_TIMESTAMP)");
            assertEquals(1,notices(operator,"").path("unreadCount").asInt());
            readNotices(operator,List.of(902L));delayed.commit();
        }
        var after=notices(operator,"");assertEquals(1,after.path("unreadCount").asInt());
        assertEquals("901",after.path("items").get(0).path("id").asText());
    }
    @Test void unreadPageFilterUsesCurrentUserAndExcludesDeletedEvents()throws Exception{
        receive(event(1,12,.8,"ENDED"));long id=jdbc.queryForObject("SELECT id FROM abnormal_event",Long.class);
        var operator=login("operator");readNotices(operator,List.of(id));
        String path="/Abnormal-event/page";
        var page=mvc.perform(get(path).servletPath(path).session(operator).param("unreadOnly","true")).andExpect(status().isOk()).andReturn();
        assertEquals(0,json.readTree(page.getResponse().getContentAsString()).path("data").path("total").asInt());
        assertEquals(1,notices(login("admin"),"").path("unreadCount").asInt());
        jdbc.update("UPDATE abnormal_event SET deleted=1 WHERE id=?",id);
        assertEquals(0,notices(login("admin"),"").path("unreadCount").asInt());
    }
    @Test void noticeEndpointsRequireLoginCsrfAndBoundedPositiveIds()throws Exception{
        mvc.perform(get("/alarm-notices").servletPath("/alarm-notices")).andExpect(status().isUnauthorized());
        var operator=login("operator");
        mvc.perform(post("/alarm-notices/read").servletPath("/alarm-notices/read").session(operator).contentType("application/json").content("{\"ids\":[1]}")).andExpect(status().isForbidden());
        mvc.perform(csrf(post("/alarm-notices/read").servletPath("/alarm-notices/read"),operator).contentType("application/json").content("{\"ids\":[-1]}")).andExpect(status().isBadRequest());
        mvc.perform(get("/alarm-notices").servletPath("/alarm-notices").session(operator).param("size","101")).andExpect(status().isBadRequest());
        readNotices(operator,List.of(99999L));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_notice_read",Integer.class));
    }
    private RiskPolicy policy(int dwell){return new RiskPolicy(true,List.of(12),0,0,1,1,.5,dwell,3,60,3,180,1);}
    private void configured(RiskPolicy policy)throws Exception{
        jdbc.update("DELETE FROM session_risk_policy WHERE session_id=?",session);
        jdbc.update("INSERT INTO session_risk_policy VALUES(?,?)",session,json.writeValueAsString(policy.values()));
    }
    private ObjectNode live(long sequence,double offset,String state){
        var e=event(sequence,12,.8,state);e.put("protocolVersion",4);
        e.put("lastSeen",observedAt.plusMillis(Math.round(offset*1000)).toString());
        e.put("observedThrough",e.path("lastSeen").asText());return e;
    }
    private ObjectNode missing(long sequence,double last,double through){
        var e=live(sequence,last,"MISSING");e.put("observedThrough",observedAt.plusMillis(Math.round(through*1000)).toString());
        e.put("missingSince",observedAt.plusMillis(Math.round((last+.1)*1000)).toString());return e;
    }
    private long alarmId(){return jdbc.queryForObject("SELECT id FROM abnormal_event ORDER BY id DESC LIMIT 1",Long.class);}
    private String riskState(){return jdbc.queryForObject("SELECT state FROM risk_incident ORDER BY alarm_id DESC LIMIT 1",String.class);}
    @Test void p1UnconfiguredDetectionIsAnObservationNotAnAutomaticRisk(){
        assertEquals("APPLIED",receive(live(1,0,"ACTIVE")).get("status"));
        assertEquals("OBSERVATION",jdbc.queryForObject("SELECT kind FROM risk_incident",String.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_notice",Integer.class));
    }
    @Test void p1RuleRequiresCurrentConfidenceAndContinuousDwell()throws Exception{
        configured(policy(2));
        var low=live(1,0,"ACTIVE");low.put("confidence",.3);receive(low);
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        receive(live(2,1,"ACTIVE"));receive(live(3,2,"ACTIVE"));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        receive(live(4,3,"ACTIVE"));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals("RISK",jdbc.queryForObject("SELECT kind FROM risk_incident",String.class));
    }
    @Test void p1ShortMissingKeepsOneIncidentAndExplicitAbsenceClearsIt()throws Exception{
        configured(policy(0));receive(live(1,0,"ACTIVE"));receive(missing(2,0,1));assertEquals("MISSING",riskState());
        receive(live(3,2,"ACTIVE"));assertEquals("PRESENT",riskState());
        var ended=missing(4,2,6);ended.put("state","ENDED");ended.put("reason","confirmed_absence");
        receive(ended);assertEquals("CLEARED",riskState());assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void p1TooShortAbsenceIsRejectedInsteadOfClearingRisk()throws Exception{
        configured(policy(0));receive(live(1,0,"ACTIVE"));
        var ended=missing(2,0,1);ended.put("state","ENDED");ended.put("reason","confirmed_absence");
        assertEquals("REJECTED",receive(ended).get("status"));assertEquals("PRESENT",riskState());
    }
    @Test void p1StoppingMonitoringDoesNotMeanTheRiskWasCleared()throws Exception{
        configured(policy(0));receive(live(1,0,"ACTIVE"));monitoring.setEnabled(1,false);
        assertEquals("INTERRUPTED",riskState());assertEquals(0,jdbc.queryForObject("SELECT status FROM abnormal_event",Integer.class));
    }
    @Test void p1UniqueCompatibleFragmentIsLinkedAndOtherVisibleSourcePreventsFalseClear()throws Exception{
        configured(policy(0));receive(live(1,0,"ACTIVE"));receive(missing(2,0,.1));
        var second=live(1,1,"ACTIVE");second.put("trackId","2");second.put("firstSeen",observedAt.plusSeconds(1).toString());receive(second);
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_source_link",Integer.class));
        var later=second.deepCopy();later.put("eventId",UUID.randomUUID().toString().replace("-",""));later.put("sequence",2);later.put("lastSeen",observedAt.plusSeconds(4).toString());later.put("observedThrough",later.path("lastSeen").asText());later.with("classEvidence").with("12").put("count",2);receive(later);
        var oldEnd=missing(3,0,4);oldEnd.put("state","ENDED");oldEnd.put("reason","confirmed_absence");receive(oldEnd);
        assertEquals("PRESENT",riskState());assertEquals("ACTIVE",jdbc.queryForObject("SELECT detection_state FROM abnormal_event",String.class));
    }
    @Test void p1AmbiguousFragmentsAreNotBlindlyCombined()throws Exception{
        configured(policy(0));receive(live(1,0,"ACTIVE"));
        var other=live(1,0,"ACTIVE");other.put("trackId","2");receive(other);
        receive(missing(2,0,.1));var otherMissing=missing(2,0,.1);otherMissing.put("trackId","2");receive(otherMissing);
        var third=live(1,1,"ACTIVE");third.put("trackId","3");third.put("firstSeen",observedAt.plusSeconds(1).toString());receive(third);
        assertEquals(3,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals("AMBIGUOUS_NEW",jdbc.queryForObject("SELECT association FROM risk_incident ORDER BY alarm_id DESC LIMIT 1",String.class));
    }
    @Test void p1OutsideRegionThenReentryCreatesAnotherEpisodeOnTheSameTrack()throws Exception{
        configured(new RiskPolicy(true,List.of(12),0,0,.5,1,.5,0,3,60,3,180,1));receive(live(1,0,"ACTIVE"));
        var outside=live(2,1,"ACTIVE");outside.putArray("bbox").add(400).add(20).add(500).add(120);receive(outside);
        outside=outside.deepCopy();outside.put("eventId",UUID.randomUUID().toString().replace("-",""));outside.put("sequence",3);outside.put("lastSeen",observedAt.plusSeconds(4).toString());outside.put("observedThrough",outside.path("lastSeen").asText());outside.with("classEvidence").with("12").put("count",3);receive(outside);
        assertEquals("CLEARED",riskState());receive(live(4,5,"ACTIVE"));
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));assertEquals("PRESENT",riskState());
    }
    @Test void p1OneMinuteCreatesOneEventAndOnePersistentReminderEvenAfterReadAndResolution()throws Exception{
        configured(policy(0));observedAt=Instant.now().minusSeconds(59);receive(live(1,0,"ACTIVE"));long alarm=alarmId();
        var operator=login("operator");readNotices(operator,List.of(alarm));
        jdbc.update("UPDATE abnormal_event SET status=2,handler_id=2,handle_result='checked'");
        for(int second=1;second<=60;second++)receive(live(second+1,second,"ACTIVE"));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_notice WHERE kind='ONGOING'",Integer.class));
        assertEquals(1,notices(operator,"").path("unreadCount").asInt());
        assertEquals("ONGOING",notices(operator,"").path("items").get(0).path("kind").asText());
        assertEquals(2,jdbc.queryForObject("SELECT status FROM abnormal_event",Integer.class));
        assertEquals("checked",jdbc.queryForObject("SELECT handle_result FROM abnormal_event",String.class));
    }
    @Test void p1OldReplayAndMediaTimeDoNotCreateContinuousRiskNotifications()throws Exception{
        configured(policy(0));observedAt=Instant.now().minusSeconds(120);
        var first=live(1,0,"ACTIVE");first.put("timeSource","media_time");receive(first);
        var later=live(2,60,"ACTIVE");later.put("timeSource","media_time");receive(later);receive(later);
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_notice",Integer.class));
    }
    @Test void p1NotificationReadDoesNotConsumeFutureReminder()throws Exception{
        configured(policy(0));observedAt=Instant.now().minusSeconds(59);receive(live(1,0,"ACTIVE"));
        var operator=login("operator");String firstId=notices(operator,"").path("items").get(0).path("noticeId").asText();
        receive(live(2,60,"ACTIVE"));
        mvc.perform(csrf(post("/alarm-notices/read").servletPath("/alarm-notices/read"),operator).contentType("application/json").content("{\"noticeIds\":[\""+firstId+"\"]}")).andExpect(status().isOk());
        assertEquals(1,notices(operator,"").path("unreadCount").asInt());
    }
    @Test void p1RiskRulesRequireAdminStoppedTaskAndValidGeometry()throws Exception{
        String path="/camera/1/risk-rule";var admin=login("admin");var body=json.valueToTree(policy(2).values());((ObjectNode)body).put("revision",0);
        mvc.perform(csrf(put(path).servletPath(path),admin).contentType("application/json").content(body.toString())).andExpect(status().isConflict());
        monitoring.setEnabled(1,false);
        mvc.perform(csrf(put(path).servletPath(path),login("operator")).contentType("application/json").content(body.toString())).andExpect(status().isForbidden());
        ((ObjectNode)body).putArray("roi").add(.8).add(0).add(.2).add(1);
        mvc.perform(csrf(put(path).servletPath(path),admin).contentType("application/json").content(body.toString())).andExpect(status().isBadRequest());
    }
    private byte[] jpeg(int rgb)throws Exception{
        var picture=new java.awt.image.BufferedImage(8,8,java.awt.image.BufferedImage.TYPE_INT_RGB);picture.setRGB(3,3,rgb);
        var bytes=new java.io.ByteArrayOutputStream();javax.imageio.ImageIO.write(picture,"JPEG",bytes);return bytes.toByteArray();
    }
    private com.fasterxml.jackson.databind.JsonNode ruleRequest(MockHttpSession user,MockHttpServletRequestBuilder request,Object body,int statusCode)throws Exception{
        if(body!=null)request=csrf(request,user).contentType("application/json").content(json.writeValueAsString(body));
        var response=mvc.perform(request.session(user)).andExpect(status().is(statusCode)).andReturn().getResponse();
        return json.readTree(response.getContentAsByteArray()).path("data");
    }
    private long templateAlarm(long camera,Map<String,Object> task)throws Exception{
        var note=live(1,0,"ACTIVE");
        note.put("sessionId",task.get("session_id").toString()).put("cameraId",String.valueOf(camera))
            .put("generation",((Number)task.get("generation")).longValue());
        assertEquals("APPLIED",receive(note).get("status"));
        return jdbc.queryForObject("SELECT alarm_id FROM risk_incident WHERE session_id=? AND kind='RISK'",Long.class,task.get("session_id"));
    }
    @Test void riskTemplatesPinDefaultsPreserveLocalOverridesAndHistoricalAlarms()throws Exception{
        var admin=login("admin");
        var operator=login("operator");
        String catalog="/risk-templates";
        var seeded=ruleRequest(admin,get(catalog),null,200);
        assertTrue(seeded.path("versions").size()>=2);
        var params=(ObjectNode)json.valueToTree(policy(0).values());
        var edit=json.createObjectNode().put("name","测试场景");
        edit.set("parameters",params);
        ruleRequest(operator,post(catalog),edit,403);
        var v1=ruleRequest(admin,post(catalog),edit,200);
        String id=v1.path("id").asText();
        String versions=catalog+"/"+id+"/versions", upgrade=catalog+"/"+id+"/2/upgrade";
        long defaultRevision=seeded.path("recommendation").path("revision").asLong();
        var recommendation=Map.of("revision",defaultRevision,"template",Map.of("id",id,"version",1));
        ruleRequest(admin,put(catalog+"/default"),recommendation,200);
        ruleRequest(admin,put(catalog+"/default"),recommendation,409);
        try{
            long[] ids=new long[2];
            for(int i=0;i<2;i++){
                ids[i]=ruleRequest(admin,post("/camera"),Map.of("name","template-"+i,"location","test","rtspUrl","rtsp://127.0.0.1:8554/test"),200).asLong();
                String path="/camera/"+ids[i]+"/risk-rule";
                var local=(ObjectNode)ruleRequest(operator,get(path),null,200);
                assertFalse(local.path("enabled").asBoolean());assertEquals(1,local.at("/template/version").asInt());
                local.put("enabled",true);
                local.putArray("roi").add(0).add(0).add(i==0?.45:.75).add(1);
                if(i==0)local.put("confidence",.75);
                ruleRequest(admin,put(path),local,200);
            }
            long a=ids[0], b=ids[1];
            assertFalse(ruleRequest(operator,get("/camera/1/risk-rule"),null,200).hasNonNull("template"));
            var oldTask=monitoring.setEnabled(a,true);
            long oldAlarm=templateAlarm(a,oldTask);
            assertEquals(1,ruleRequest(operator,get("/camera/"+a+"/risk-rule/effective"),null,200).at("/template/version").asInt());
            var otherTask=monitoring.setEnabled(b,true);
            params.put("confidence",.65).put("level",4);
            edit.put("previous",1);
            ruleRequest(admin,post(versions),edit,200);
            ruleRequest(admin,post(versions),edit,409);
            assertEquals(1,ruleRequest(admin,get(catalog),null,200).at("/recommendation/template/version").asInt());
            var impact=ruleRequest(admin,get(catalog+"/"+id+"/2/impact"),null,200);
            assertEquals(2,impact.size());assertTrue(impact.get(0).path("running").asBoolean());
            assertEquals(.75,impact.get(0).at("/after/confidence").asDouble());
            assertEquals(.65,impact.get(1).at("/after/confidence").asDouble());
            monitoring.setEnabled(a,false);
            var selection=List.of(Map.of("cameraId",a,"revision",2),Map.of("cameraId",b,"revision",2));
            ruleRequest(admin,post(upgrade),selection,409);
            var path="/camera/"+a+"/risk-rule";
            assertEquals(2,ruleRequest(operator,get(path),null,200).path("revision").asInt());
            ruleRequest(operator,post(upgrade),List.of(selection.get(0)),403);
            ruleRequest(admin,post(upgrade),List.of(selection.get(0)),200);
            ruleRequest(admin,post(upgrade),List.of(selection.get(0)),409);
            long newAlarm=templateAlarm(a,monitoring.setEnabled(a,true));
            long otherAlarm=templateAlarm(b,otherTask);
            for(long alarm:List.of(oldAlarm,newAlarm,otherAlarm)){
                var insight=ruleRequest(operator,get("/Abnormal-event/"+alarm+"/insight"),null,200);
                var snapshot=json.readTree(insight.at("/risk/0/policy").asText());
                assertEquals(alarm==newAlarm?2:1,snapshot.at("/template/version").asInt());
                assertEquals(alarm==otherAlarm?.75:.45,snapshot.at("/roi/2").asDouble());
                assertEquals(alarm==newAlarm?4:3,snapshot.path("level").asInt());
            }
            // A later default that temporarily matches the local override must not erase it.
            params.put("confidence",.75);edit.put("previous",2);
            ruleRequest(admin,post(versions),edit,200);
            monitoring.setEnabled(a,false);
            ruleRequest(admin,post(catalog+"/"+id+"/3/upgrade"),List.of(Map.of("cameraId",a,"revision",3)),200);
            params.put("confidence",.9);edit.put("previous",3);
            ruleRequest(admin,post(versions),edit,200);
            var finalImpact=ruleRequest(admin,get(catalog+"/"+id+"/4/impact"),null,200);
            assertEquals(.75,finalImpact.get(0).at("/after/confidence").asDouble());
            var history=ruleRequest(admin,get(path+"/history"),null,200);
            assertEquals(4,history.size());assertEquals(1,history.get(0).path("actor_id").asLong());
            assertTrue(history.get(0).hasNonNull("changed_at"));
            var page=ruleRequest(operator,get("/camera/page").param("name","template-0"),null,200);
            assertEquals(3,page.at("/records/0/riskRule/template/version").asInt());
        }finally{
            // Restore the isolated fixture's default for the rest of the suite.
            jdbc.update("UPDATE risk_template_default SET template_id=NULL,version_no=NULL WHERE singleton_id=1");
        }
    }
    private MockHttpServletRequestBuilder evidenceRequest(String event){return post("/_evidence/"+event).servletPath("/_evidence/"+event).header("Authorization","Bearer isolated-evidence-service-key-at-least-32-characters").header("X-Worker-Id","detector-1").contentType("image/jpeg");}
    @Test void p1ScreenshotUploadIsDurableIdempotentAndAuthenticated()throws Exception{
        var e=live(1,0,"ACTIVE");receive(e);String id=e.path("eventId").asText();byte[] bytes=jpeg(0x00ff00);
        mvc.perform(evidenceRequest(id).content(bytes)).andExpect(status().isOk());
        mvc.perform(evidenceRequest(id).content(bytes)).andExpect(status().isOk());
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_evidence",Integer.class));
        var row=jdbc.queryForMap("SELECT id,alarm_id,file_name FROM alarm_evidence");
        assertArrayEquals(bytes,java.nio.file.Files.readAllBytes(java.nio.file.Path.of(evidenceRoot,(String)row.get("file_name"))));
        String path="/Abnormal-event/"+row.get("alarm_id")+"/evidence/"+row.get("id");
        mvc.perform(get(path).servletPath(path)).andExpect(status().isUnauthorized());
        mvc.perform(get(path).servletPath(path).session(login("operator"))).andExpect(status().isOk()).andExpect(content().bytes(bytes));
        mvc.perform(evidenceRequest(id).content(jpeg(0xff0000))).andExpect(status().isConflict());
    }
    @Test void p1ScreenshotRejectsOtherIdentityPreviewTokenAndBrowserOrigin()throws Exception{
        var e=live(1,0,"ACTIVE");receive(e);String id=e.path("eventId").asText();byte[] bytes=jpeg(0);
        mvc.perform(evidenceRequest(id).header("Origin","http://localhost:3000").content(bytes)).andExpect(status().isUnauthorized());
        mvc.perform(post("/_evidence/"+id).servletPath("/_evidence/"+id).header("Authorization","Bearer isolated-test-service-key-32-characters-long").header("X-Worker-Id","detector-1").contentType("image/jpeg").content(bytes)).andExpect(status().isUnauthorized());
        mvc.perform(post("/_evidence/"+id).servletPath("/_evidence/"+id).header("Authorization","Bearer isolated-evidence-service-key-at-least-32-characters").header("X-Worker-Id","detector-2").contentType("image/jpeg").content(bytes)).andExpect(status().isUnauthorized());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_evidence",Integer.class));
    }
    @Test void p1ScreenshotWaitsForMetadataAndRejectsMalformedOrLargeImages()throws Exception{
        mvc.perform(evidenceRequest("a".repeat(32)).content(jpeg(0))).andExpect(status().is(425));
        var e=live(1,0,"ACTIVE");receive(e);String id=e.path("eventId").asText();
        mvc.perform(evidenceRequest(id).content("not a JPEG")).andExpect(status().isBadRequest());
        mvc.perform(evidenceRequest(id).content(new byte[2*1024*1024+1])).andExpect(status().is(413));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void p1ScreenshotQuotaAndPerIncidentLimitNeverRetractAlarms()throws Exception{
        for(int i=1;i<=4;i++){
            var e=live(i,0,"ACTIVE");receive(e);mvc.perform(evidenceRequest(e.path("eventId").asText()).content(jpeg(i*5000))).andExpect(status().isOk());
        }
        assertEquals(3,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_evidence",Integer.class));
        var another=live(1,0,"ACTIVE");another.put("trackId","99");receive(another);
        var controller=org.springframework.test.util.AopTestUtils.getUltimateTargetObject(application.getBean(com.example.controller.EvidenceController.class));
        Object old=org.springframework.test.util.ReflectionTestUtils.getField(controller,"quota");
        try{
            org.springframework.test.util.ReflectionTestUtils.setField(controller,"quota",1L);
            mvc.perform(evidenceRequest(another.path("eventId").asText()).content(jpeg(100))).andExpect(status().is(507));
        }finally{org.springframework.test.util.ReflectionTestUtils.setField(controller,"quota",old);}
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void p1DeletedAlarmAndWrongBindingCannotExposeEvidence()throws Exception{
        var e=live(1,0,"ACTIVE");receive(e);mvc.perform(evidenceRequest(e.path("eventId").asText()).content(jpeg(100))).andExpect(status().isOk());
        var row=jdbc.queryForMap("SELECT id,alarm_id FROM alarm_evidence");var operator=login("operator");
        String wrong="/Abnormal-event/99999/evidence/"+row.get("id");mvc.perform(get(wrong).servletPath(wrong).session(operator)).andExpect(status().isNotFound());
        jdbc.update("UPDATE abnormal_event SET deleted=1 WHERE id=?",row.get("alarm_id"));
        String path="/Abnormal-event/"+row.get("alarm_id")+"/evidence/"+row.get("id");mvc.perform(get(path).servletPath(path).session(operator)).andExpect(status().isNotFound());
    }
    @Test void p1FirstTerminalSnapshotPreservesAnUnverifiedObservation()throws Exception{
        configured(policy(2));var end=missing(5,0,4);end.put("state","ENDED");end.put("reason","confirmed_absence");
        assertEquals("APPLIED",receive(end).get("status"));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        assertEquals("OBSERVATION",jdbc.queryForObject("SELECT kind FROM risk_incident",String.class));
        assertEquals("LATE_SNAPSHOT_REVIEW",jdbc.queryForObject("SELECT association FROM risk_incident",String.class));
        receive(live(1,0,"ACTIVE"));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void p1VisibleOutsideObjectPreventsMergingANearbyNewTarget()throws Exception{
        configured(new RiskPolicy(true,List.of(12),0,0,.5,1,.5,0,3,60,3,180,1));
        var first=live(1,0,"ACTIVE");first.putArray("bbox").add(260).add(20).add(340).add(120);receive(first);
        var outside=live(2,1,"ACTIVE");outside.putArray("bbox").add(290).add(20).add(370).add(120);receive(outside);assertEquals("MISSING",riskState());
        var second=live(1,1.5,"ACTIVE");second.put("trackId","2");second.putArray("bbox").add(270).add(20).add(330).add(120);receive(second);
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void p1CrossSessionAndDistantTargetsRemainSeparate()throws Exception{
        configured(policy(0));receive(live(1,0,"ACTIVE"));receive(missing(2,0,.1));
        var far=live(1,1,"ACTIVE");far.put("trackId","2");far.putArray("bbox").add(400).add(200).add(500).add(300);receive(far);
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
        monitoring.setEnabled(1,false);session=(String)monitoring.setEnabled(1,true).get("session_id");observedAt=Instant.now().minusSeconds(1);
        var newSession=live(1,0,"ACTIVE");newSession.put("generation",3);receive(newSession);
        assertEquals(3,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void p1RiskEscalationHasItsOwnPersistentNotification()throws Exception{
        configured(new RiskPolicy(true,List.of(12),0,0,1,1,.5,0,3,60,3,10,1));observedAt=Instant.now().minusSeconds(12);
        receive(live(1,0,"ACTIVE"));receive(live(2,11,"ACTIVE"));
        assertEquals(4,jdbc.queryForObject("SELECT risk_level FROM risk_incident",Integer.class));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_notice WHERE kind='ESCALATION'",Integer.class));
        assertEquals(3,jdbc.queryForObject("SELECT level FROM abnormal_event",Integer.class));
    }
    @Test void p1HumanActionsKeepAuditAndRuleUpdatesUseRevisionFencing()throws Exception{
        receive(live(1,0,"ACTIVE"));long alarm=alarmId();var admin=login("admin");
        mvc.perform(csrf(put("/Abnormal-event/"+alarm+"/status").servletPath("/Abnormal-event/"+alarm+"/status"),admin).contentType("application/json").content("{\"status\":2,\"version\":0,\"result\":\"checked\"}")).andExpect(status().isOk());
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_handling_audit",Integer.class));
        monitoring.setEnabled(1,false);String path="/camera/1/risk-rule";var body=(ObjectNode)json.valueToTree(policy(2).values());body.put("revision",0);
        mvc.perform(csrf(put(path).servletPath(path),admin).contentType("application/json").content(body.toString())).andExpect(status().isOk());
        mvc.perform(csrf(put(path).servletPath(path),admin).contentType("application/json").content(body.toString())).andExpect(status().isConflict());
    }


    @Test void p1ConcurrentHumanSubmissionsConflictInsteadOfOverwriting()throws Exception{
        receive(live(1,0,"ACTIVE"));long alarm=alarmId();var a=login("admin");var b=login("operator");
        String path="/Abnormal-event/"+alarm+"/handle";
        var ra=csrf(post(path).servletPath(path),a).contentType("application/json").content(json.writeValueAsString(Map.of("id",alarm,"version",0,"handleResult","first")));
        var rb=csrf(post(path).servletPath(path),b).contentType("application/json").content(json.writeValueAsString(Map.of("id",alarm,"version",0,"handleResult","second")));
        var pool=Executors.newFixedThreadPool(2);
        try{
            var barrier=new CyclicBarrier(2);
            var replies=pool.invokeAll(List.<Callable<Integer>>of(()->{barrier.await();return mvc.perform(ra).andReturn().getResponse().getStatus();},()->{barrier.await();return mvc.perform(rb).andReturn().getResponse().getStatus();}));
            assertEquals(List.of(200,409),replies.stream().map(f->{try{return f.get();}catch(Exception e){throw new RuntimeException(e);}}).sorted().toList());
        }finally{pool.shutdownNow();}
        assertEquals(1L,jdbc.queryForObject("SELECT version FROM alarm_edit_version WHERE alarm_id=?",Long.class,alarm));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_handling_audit",Integer.class));
    }
    @Test void p1MissingVersionAndIncompleteResolutionAreRejected()throws Exception{
        receive(live(1,0,"ACTIVE"));long alarm=alarmId();var user=login("operator");String path="/Abnormal-event/"+alarm+"/status";
        mvc.perform(csrf(put(path).servletPath(path),user).contentType("application/json").content("{\"status\":2}")).andExpect(status().isBadRequest());
        mvc.perform(csrf(put(path).servletPath(path),user).contentType("application/json").content("{\"status\":2,\"version\":0}")).andExpect(status().isBadRequest());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM alarm_handling_audit",Integer.class));
    }
    @Test void p1AutomaticUpdatesDoNotInvalidateHumanVersion()throws Exception{
        receive(live(1,0,"ACTIVE"));long alarm=alarmId();receive(live(2,1,"ACTIVE"));var user=login("operator");
        String path="/Abnormal-event/"+alarm+"/handle";
        mvc.perform(csrf(post(path).servletPath(path),user).contentType("application/json").content(json.writeValueAsString(Map.of("id",alarm,"version",0,"handleResult","checked")))).andExpect(status().isOk());
        receive(live(3,2,"ACTIVE"));
        assertEquals(1L,jdbc.queryForObject("SELECT version FROM alarm_edit_version WHERE alarm_id=?",Long.class,alarm));
        mvc.perform(get("/Abnormal-event/"+alarm).servletPath("/Abnormal-event/"+alarm).session(user)).andExpect(status().isOk()).andExpect(jsonPath("$.data.version").value(1));
    }
    @Test void p1StatisticsUseOrderedShanghaiDatesAndIndependentBounds(){
        var service=application.getBean(com.example.service.StatisticsService.class);
        jdbc.update("INSERT INTO abnormal_event(camera_id,location,event_time,create_time,level,status,type,source_key) VALUES(1,'test','2026-11-10 23:00:00','2026-11-10 16:30:00',1,0,'工人',?),(1,'test','2026-11-10 22:00:00','2026-11-10 22:00:00',1,2,'工人',NULL)","f".repeat(64));
        var result=service.getAbnormalEventStatistics(null,null);assertEquals(2,result.getTotalCount());
        assertEquals(List.of("2026-11-10","2026-11-11"),result.getTrendData().stream().map(row->row.get("date")).toList());
        assertEquals(1,service.getAbnormalEventStatistics("2026-11-11",null).getTotalCount());
        assertEquals(1,service.getAbnormalEventStatistics(null,"2026-11-10").getTotalCount());
        assertThrows(com.example.common.exception.BusinessException.class,()->service.getAbnormalEventStatistics("2026-11-11","2026-11-09"));
    }
    @Test void p1OverviewRecentEventsAreLimitedAndUptimeIsMeasured(){
        for(int i=0;i<12;i++)jdbc.update("INSERT INTO abnormal_event(camera_id,location,event_time,level,status,type) VALUES(1,'test',?,1,0,'工人')",java.time.LocalDateTime.now().minusMinutes(i));
        var result=application.getBean(com.example.service.StatisticsService.class).getSystemOverview();
        assertEquals(5,result.getRecentAlarms().size());
        assertEquals((int)(java.lang.management.ManagementFactory.getRuntimeMXBean().getUptime()/86400000),result.getRunningDays());
        assertEquals(0,result.getOnlineDevices());
    }
    @Test void p1HistoricalHealthIsUnknownUntilSampledAndNeverBackfilledFromCurrentCameraState(){
        var statistics=application.getBean(com.example.service.StatisticsService.class);
        assertTrue(statistics.getDeviceStatusStatistics().getOnlineRateTrend().stream().allMatch(row->row.get("rate")==null));
        var health=application.getBean(MonitoringHealthService.class);String now=Instant.now().toString();
        var metric=json.createObjectNode().put("lastFrameAt",now).put("lastInferenceAt",now).put("effectiveFps",3);
        monitoring.status("detector-1",json.createObjectNode().put("sessionId",session).put("state","RUNNING").put("revision",1).set("metrics",metric));
        assertEquals(1,health.healthyCount());
        var old=java.time.LocalDate.now(java.time.ZoneId.of("Asia/Shanghai")).minusDays(2).atTime(2,0);
        jdbc.update("UPDATE monitoring_health_sample SET observed_at=?",old);
        jdbc.update("INSERT INTO monitoring_health_sample(camera_id,session_id,enabled,state,observed_at) VALUES(1,?,TRUE,'UNAVAILABLE',?)",session,old.plusMinutes(1));
        jdbc.update("UPDATE camera SET status=0 WHERE id=1");
        var point=statistics.getDeviceStatusStatistics().getOnlineRateTrend().stream().filter(row->((Number)row.get("sampleCount")).intValue()>0).findFirst().orElseThrow();
        assertEquals(50.,((Number)point.get("rate")).doubleValue());
        assertEquals(2,((Number)point.get("knownSamples")).intValue());
    }
    @Test void p1FutureTelemetryDoesNotProduceHealthyInference(){
        String future=Instant.now().plusSeconds(3600).toString();
        var metric=json.createObjectNode().put("lastFrameAt",future).put("lastInferenceAt",future);
        monitoring.status("detector-1",json.createObjectNode().put("sessionId",session).put("state","RUNNING").put("revision",1).set("metrics",metric));
        assertEquals(0,application.getBean(MonitoringHealthService.class).healthyCount());
    }
    @Test void p1MonitoringFaultPersistsDeduplicatesAndReadDoesNotResolve()throws Exception{
        jdbc.update("UPDATE monitoring_session SET created_at=? WHERE session_id=?",java.time.LocalDateTime.now(java.time.ZoneOffset.UTC).minusMinutes(2),session);
        var sampler=application.getBean(MonitoringHealthSampler.class);
        sampler.sampleOnce();sampler.sampleOnce();assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM monitoring_fault",Integer.class));
        var a=login("operator");var b=login("admin");long id=jdbc.queryForObject("SELECT id FROM monitoring_fault",Long.class);
        String path="/monitoring/faults";
        mvc.perform(csrf(post(path+"/read").servletPath(path+"/read"),a).contentType("application/json").content(json.writeValueAsString(Map.of("ids",List.of(id))))).andExpect(status().isOk());
        mvc.perform(get(path).servletPath(path).session(a)).andExpect(status().isOk()).andExpect(jsonPath("$.data.openCount").value(1)).andExpect(jsonPath("$.data.unreadCount").value(0));
        mvc.perform(get(path).servletPath(path).session(b)).andExpect(status().isOk()).andExpect(jsonPath("$.data.unreadCount").value(1));
        monitoring.setEnabled(1,false);monitoring.commands();
        assertEquals("MONITORING_DISABLED",jdbc.queryForObject("SELECT closed_reason FROM monitoring_fault",String.class));
    }
    @Test void p1ReadinessSeparatesDatabaseAndProcessLiveness()throws Exception{
        mvc.perform(get("/health/live").servletPath("/health/live")).andExpect(status().isOk());
        mvc.perform(get("/health/ready").servletPath("/health/ready")).andExpect(status().isOk());
        var controller=new com.example.controller.HealthController(new JdbcTemplate(),application.getBean(MqttBridge.class));
        assertEquals(503,controller.ready().getStatusCode().value());
        assertEquals("UP",controller.live().get("status"));
    }


    @Test void p1SmsSignerMatchesTheOfficialAcs3FixedVector()throws Exception{
        var headers=NotificationTransport.signedHeaders("YourAccessKeyId","YourAccessKeySecret","ecs.cn-shanghai.aliyuncs.com","RunInstances","2014-05-26","2023-10-26T10:22:32Z","3156853299f313e23d1673dc12e1703d","ImageId=win2019_1809_x64_dtc_zh-cn_40G_alibase_20230811.vhd&RegionId=cn-shanghai");
        assertTrue(headers.get("Authorization").endsWith("06563a9e1b43f5dfe96b81484da74bceab24a1d853912eee15083a6f0f3283c0"));
    }
    private void webhook(String url){
        var transport=application.getBean(NotificationTransport.class);
        org.springframework.test.util.ReflectionTestUtils.setField(transport,"webhookUrl",url);
        org.springframework.test.util.ReflectionTestUtils.setField(transport,"webhookKey","isolated-webhook-key-at-least-32-characters");
        org.springframework.test.util.ReflectionTestUtils.setField(transport,"loopback",true);
    }
    @Test void p1WebhookRetriesWithTheSameIdentityAndNeverDuplicatesTheNotice()throws Exception{
        var server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
        var identities=new java.util.concurrent.CopyOnWriteArrayList<String>();var signatures=new java.util.concurrent.CopyOnWriteArrayList<Boolean>();
        server.createContext("/hook",exchange->{
            try{
                byte[] body=exchange.getRequestBody().readAllBytes();String id=exchange.getRequestHeaders().getFirst("X-Notification-Id"),time=exchange.getRequestHeaders().getFirst("X-Notification-Time");identities.add(id);
                signatures.add(NotificationTransport.hmac("isolated-webhook-key-at-least-32-characters",id+"\n"+time+"\n"+NotificationTransport.sha(body)).equals(exchange.getRequestHeaders().getFirst("X-Notification-Signature")));
                exchange.sendResponseHeaders(identities.size()==1?429:200,-1);
            }catch(Exception e){throw new RuntimeException(e);}finally{exchange.close();}
        });server.start();
        try{
            webhook("http://127.0.0.1:"+server.getAddress().getPort()+"/hook");configured(policy(0));var event=live(1,0,"ACTIVE");receive(event);receive(event);
            assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM notification_delivery",Integer.class));
            var outbox=application.getBean(NotificationOutbox.class);assertTrue(outbox.dispatchOnce());
            assertEquals("RETRY",jdbc.queryForObject("SELECT status FROM notification_delivery",String.class));
            jdbc.update("UPDATE notification_delivery SET next_at=?",java.time.LocalDateTime.now(java.time.ZoneOffset.UTC).minusSeconds(1));
            assertTrue(outbox.dispatchOnce());assertEquals("ACKNOWLEDGED",jdbc.queryForObject("SELECT status FROM notification_delivery",String.class));
            assertEquals(2,identities.size());assertEquals(identities.get(0),identities.get(1));assertEquals(List.of(true,true),signatures);
        }finally{server.stop(0);}
    }
    @Test void p1ExternalNotificationIsAtomicWithTheAlarmAndObservationDoesNotSend()throws Exception{
        webhook("http://127.0.0.1:1/hook");receive(live(1,0,"ACTIVE"));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM notification_delivery",Integer.class));
        monitoring.setEnabled(1,false);configured(policy(0));session=(String)monitoring.setEnabled(1,true).get("session_id");
        var event=live(1,0,"ACTIVE");event.put("generation",3);
        jdbc.execute("ALTER TABLE detection_receipt ADD COLUMN injected_failure INTEGER DEFAULT 0");
        try{assertThrows(org.springframework.dao.DataAccessException.class,()->receive(event));}
        finally{jdbc.execute("ALTER TABLE detection_receipt DROP COLUMN injected_failure");}
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM notification_delivery",Integer.class));
    }
    @Test void p1SmsProcessLossLeavesUnknownRatherThanAutomaticallySendingTwice(){
        String id="c".repeat(32);var old=java.time.LocalDateTime.now(java.time.ZoneOffset.UTC).minusMinutes(2);
        jdbc.update("INSERT INTO notification_delivery(id,entity_type,entity_id,channel,target,payload,status,phase,attempts,next_at,lease_until,created_at,updated_at) VALUES(?,'NOTICE',1,'SMS','13800000000','{}','SENDING','SEND',1,?,?,?,?)",id,old,old,old,old);
        assertFalse(application.getBean(NotificationOutbox.class).dispatchOnce());
        assertEquals("UNKNOWN",jdbc.queryForObject("SELECT status FROM notification_delivery WHERE id=?",String.class,id));
    }
    private ObjectNode clip()throws Exception{
        String name="1_"+session+"_abcdefabcdef_000001.mp4";var root=java.nio.file.Path.of(recordingRoot);java.nio.file.Files.createDirectories(root);
        byte[] bytes=new byte[64];java.nio.ByteBuffer.wrap(bytes).putInt(24).put("ftyp".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
        java.nio.file.Files.write(root.resolve(name),bytes);String digest=NotificationTransport.sha(bytes);
        var value=json.createObjectNode().put("workerId","detector-1").put("cameraId","1").put("sessionId",session).put("file",name).put("sha256",digest).put("bytes",bytes.length).put("kind","FULL_SOURCE").put("clockSource","RECORDER_WALL_CLOCK_ESTIMATE").put("startedAt",observedAt.toString()).put("endedAt",Instant.now().toString());
        value.put("id",DetectionIngestService.hash("detector-1\n"+session+"\n"+name+"\n"+digest));return value;
    }
    private MockHttpServletRequestBuilder recordingRequest(ObjectNode value){return post("/_evidence/recordings").servletPath("/_evidence/recordings").header("Authorization","Bearer isolated-evidence-service-key-at-least-32-characters").header("X-Worker-Id","detector-1").contentType("application/json").content(value.toString());}
    @Test void p1RecordingRegistrationIsIdempotentBoundToTheAlarmAndSupportsRanges()throws Exception{
        receive(live(1,0,"ACTIVE"));long alarm=alarmId();var value=clip();
        mvc.perform(recordingRequest(value)).andExpect(status().isOk());mvc.perform(recordingRequest(value)).andExpect(status().isOk());
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM recording_clip",Integer.class));
        String path="/Abnormal-event/"+alarm+"/recordings/"+value.path("id").asText();
        mvc.perform(get(path).servletPath(path)).andExpect(status().isUnauthorized());
        mvc.perform(get(path).servletPath(path).session(login("operator")).header("Range","bytes=0-11")).andExpect(status().isPartialContent()).andExpect(header().string("Content-Range","bytes 0-11/64"));
        var changed=value.deepCopy().put("bytes",63);mvc.perform(recordingRequest(changed)).andExpect(status().isConflict());
    }
    @Test void p1RecordingRejectsWrongCameraOriginAndCorruptFiles()throws Exception{
        var value=clip();mvc.perform(recordingRequest(value).header("Origin","http://localhost:3000")).andExpect(status().isUnauthorized());
        var wrong=value.deepCopy().put("cameraId","2");mvc.perform(recordingRequest(wrong)).andExpect(status().isBadRequest());
        java.nio.file.Files.write(java.nio.file.Path.of(recordingRoot,value.path("file").asText()),new byte[64]);
        mvc.perform(recordingRequest(value)).andExpect(status().isConflict());
    }
    @Test void p1RecordingExpiryRetainsMetadataAndDoesNotPretendTheVideoExists()throws Exception{
        var value=clip();mvc.perform(recordingRequest(value)).andExpect(status().isOk());
        jdbc.update("UPDATE recording_clip SET ended_at=?",java.time.LocalDateTime.now(java.time.ZoneOffset.UTC).minusDays(31));
        String path="/camera/1/recordings/"+value.path("id").asText();
        mvc.perform(get(path).servletPath(path).session(login("operator"))).andExpect(status().isGone());
        application.getBean(com.example.controller.RecordingController.class).expire();
        assertNotNull(jdbc.queryForObject("SELECT expired_at FROM recording_clip",java.time.LocalDateTime.class));
        assertFalse(java.nio.file.Files.exists(java.nio.file.Path.of(recordingRoot,value.path("file").asText())));
    }
    @Test void p1RecordingBudgetFailureKeepsTheAlarmAndCanBeRetried()throws Exception{
        receive(live(1,0,"ACTIVE"));var value=clip();
        var controller=org.springframework.test.util.AopTestUtils.getUltimateTargetObject(application.getBean(com.example.controller.RecordingController.class));
        Object budget=org.springframework.test.util.ReflectionTestUtils.getField(controller,"budget");
        try{org.springframework.test.util.ReflectionTestUtils.setField(controller,"budget",1L);mvc.perform(recordingRequest(value)).andExpect(status().is(507));}
        finally{org.springframework.test.util.ReflectionTestUtils.setField(controller,"budget",budget);}
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));mvc.perform(recordingRequest(value)).andExpect(status().isOk());
    }
    private ObjectNode viewFrame(long sequence,Instant stamp)throws Exception{
        var value=json.createObjectNode().put("version",1).put("workerId","detector-1").put("cameraId","1").put("sessionId",session).put("generation",1).put("frameSeq",sequence).put("sourceFrameSeq",sequence*10).put("observedAt",stamp.toString()).put("processedAt",stamp.plusMillis(100).toString()).put("modelSha256","f".repeat(64)).put("width",8).put("height",8).put("sourceWidth",640).put("sourceHeight",480).put("quality","DECODE_CHECKED").put("timeSource","DECODER_RECEIVED_AT").put("totalObjects",1).put("truncated",false).put("jpeg",Base64.getEncoder().encodeToString(jpeg(123)));
        var object=value.putArray("objects").addObject().put("classId",12).put("className","worker").put("label","工人").put("confidence",.7).put("trackId","7");object.putArray("bbox").add(.1).add(.1).add(.5).add(.6);value.putArray("trails");return value;
    }
    private MockHttpServletRequestBuilder liveFrameRequest(ObjectNode value){return post("/_evidence/live-frame").servletPath("/_evidence/live-frame").header("Authorization","Bearer isolated-evidence-service-key-at-least-32-characters").header("X-Worker-Id","detector-1").contentType("application/json").content(value.toString());}
    @Test void liveFrameIsSharedAuthenticatedOrderedAndFreshEmptyIsNotAnError()throws Exception{
        jdbc.update("UPDATE monitoring_task SET state='RUNNING'");var first=viewFrame(1,Instant.now().minusSeconds(1));
        mvc.perform(liveFrameRequest(first)).andExpect(status().isOk());var second=first.deepCopy().put("frameSeq",2).put("sourceFrameSeq",20).put("totalObjects",0);second.putArray("objects");
        mvc.perform(liveFrameRequest(second)).andExpect(status().isOk());mvc.perform(liveFrameRequest(first)).andExpect(status().isOk());
        String path="/monitoring/1/frame";mvc.perform(get(path).servletPath(path)).andExpect(status().isUnauthorized());
        mvc.perform(get(path).servletPath(path).session(login("operator"))).andExpect(status().isOk()).andExpect(jsonPath("$.data.state").value("FRESH")).andExpect(jsonPath("$.data.frame.frameSeq").value(2)).andExpect(jsonPath("$.data.frame.objects.length()").value(0));
        mvc.perform(get(path).servletPath(path).param("after","2").param("session",session).session(login("operator"))).andExpect(jsonPath("$.data.unchanged").value(true)).andExpect(jsonPath("$.data.frame").doesNotExist());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM abnormal_event",Integer.class));
    }
    @Test void liveFrameRejectsWrongSessionGenerationAndBrowserUploads()throws Exception{
        String path="/monitoring/1/frame";mvc.perform(get(path).servletPath(path).session(login("operator"))).andExpect(jsonPath("$.data.state").value("WAITING"));
        jdbc.update("UPDATE monitoring_task SET state='RUNNING'");var value=viewFrame(1,Instant.now().minusSeconds(1));
        mvc.perform(liveFrameRequest(value.deepCopy().put("generation",2))).andExpect(status().isConflict());
        mvc.perform(liveFrameRequest(value.deepCopy().put("sessionId","b".repeat(32)))).andExpect(status().isConflict());
        mvc.perform(liveFrameRequest(value).header("Origin","http://localhost:3000")).andExpect(status().isUnauthorized());
        monitoring.setEnabled(1,false);mvc.perform(liveFrameRequest(value)).andExpect(status().isConflict());
    }
    @Test void liveFrameRejectsImageDimensionMismatchAndInvalidCoordinates()throws Exception{
        jdbc.update("UPDATE monitoring_task SET state='RUNNING'");var value=viewFrame(1,Instant.now().minusSeconds(1));
        mvc.perform(liveFrameRequest(value.deepCopy().put("width",16))).andExpect(status().isBadRequest());
        var bad=value.deepCopy();((ObjectNode)bad.path("objects").get(0)).putArray("bbox").add(-1).add(0).add(.5).add(.5);
        mvc.perform(liveFrameRequest(bad)).andExpect(status().isBadRequest());
        mvc.perform(liveFrameRequest(value).content(new byte[512*1024+1])).andExpect(status().is(413));
        mvc.perform(liveFrameRequest(value).content("{")).andExpect(status().isBadRequest());mvc.perform(liveFrameRequest(value).content("null")).andExpect(status().isBadRequest());
    }
    @Test void liveFrameExpiresAndSourceFailureNeverReturnsTheOldPicture()throws Exception{
        jdbc.update("UPDATE monitoring_task SET state='RUNNING'");mvc.perform(liveFrameRequest(viewFrame(1,Instant.now().minusSeconds(10)))) .andExpect(status().isOk());
        String path="/monitoring/1/frame";var user=login("operator");
        mvc.perform(get(path).servletPath(path).session(user)).andExpect(jsonPath("$.data.state").value("EXPIRED")).andExpect(jsonPath("$.data.frame").doesNotExist());
        jdbc.update("UPDATE monitoring_task SET state='FAILED'");mvc.perform(get(path).servletPath(path).session(user)).andExpect(jsonPath("$.data.state").value("SOURCE_ERROR"));
        monitoring.setEnabled(1,false);mvc.perform(get(path).servletPath(path).session(user)).andExpect(jsonPath("$.data.state").value("DISABLED"));
    }
    private ObjectNode sampleClip()throws Exception{
        var value=clip().put("kind","DETECTION_SAMPLES").put("clockSource","INFERENCE_SAMPLES_RECEIVED_AT");
        Instant start=java.time.OffsetDateTime.parse(value.path("startedAt").asText()).toInstant();value.put("endedAt",start.plusMillis(1250).toString());
        var manifest=viewFrame(1,start);manifest.remove(List.of("jpeg","workerId","frameSeq","sourceFrameSeq","observedAt","processedAt","quality","objects","totalObjects","truncated","trails","timeSource"));
        manifest.put("kind","DETECTION_SAMPLES").put("timeSource","DECODER_RECEIVED_AT").put("sourceTimestampVerified",false).put("maxSampleFps",2).put("durationMs",1250).put("frameCount",2).put("droppedSamples",0);
        var frames=manifest.putArray("frames");for(int index=0;index<2;index++){var frame=viewFrame(index+1,start.plusMillis(index*750));frame.remove(List.of("jpeg","workerId","version","cameraId","sessionId","generation","modelSha256","width","height","sourceWidth","sourceHeight","timeSource"));frame.put("offsetMs",index*750);frames.add(frame);}
        String body=json.writeValueAsString(manifest);value.put("analysisSha256",DetectionIngestService.hash(body)).put("analysisBytes",body.getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
        var envelope=json.createObjectNode().set("registration",value);((ObjectNode)envelope).put("analysisJson",body);
        java.nio.file.Files.writeString(java.nio.file.Path.of(recordingRoot,value.path("file").asText().replace(".mp4",".analysis.json")),json.writeValueAsString(envelope));return value;
    }
    @Test void sampleRecordingKeepsOriginalKindDistinctAndMetadataAuthenticated()throws Exception{
        receive(live(1,0,"ACTIVE"));long alarm=alarmId();var value=sampleClip();mvc.perform(recordingRequest(value)).andExpect(status().isOk());mvc.perform(recordingRequest(value)).andExpect(status().isOk());
        String path="/camera/1/recordings/"+value.path("id").asText()+"/analysis";
        mvc.perform(get(path).servletPath(path)).andExpect(status().isUnauthorized());
        mvc.perform(get(path).servletPath(path).session(login("operator"))).andExpect(status().isOk()).andExpect(jsonPath("$.data.frames[1].offsetMs").value(750)).andExpect(jsonPath("$.data.frames[1].objects[0].confidence").value(.7));
        String list="/camera/1/recordings";mvc.perform(get(list).servletPath(list).session(login("operator"))).andExpect(jsonPath("$.data.items[0].kind").value("DETECTION_SAMPLES"));
        String wrong="/camera/2/recordings/"+value.path("id").asText()+"/analysis";mvc.perform(get(wrong).servletPath(wrong).session(login("operator"))).andExpect(status().isNotFound());
        String alarmPath="/Abnormal-event/"+alarm+"/recordings/"+value.path("id").asText()+"/analysis";mvc.perform(get(alarmPath).servletPath(alarmPath).session(login("operator"))).andExpect(status().isOk());
    }
    @Test void sampleMetadataTamperingCannotRegisterAnOtherwiseValidMp4()throws Exception{
        var value=sampleClip();var path=java.nio.file.Path.of(recordingRoot,value.path("file").asText().replace(".mp4",".analysis.json"));var envelope=(ObjectNode)json.readTree(java.nio.file.Files.readString(path));envelope.put("analysisJson",envelope.path("analysisJson").asText().replace("0.7","0.9"));java.nio.file.Files.writeString(path,envelope.toString());
        mvc.perform(recordingRequest(value)).andExpect(status().isBadRequest());assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM recording_clip",Integer.class));
    }
    @Test void sampleExpiryRemovesBothFilesAndPayloadButKeepsItsType()throws Exception{
        var value=sampleClip();mvc.perform(recordingRequest(value)).andExpect(status().isOk());jdbc.update("UPDATE recording_clip SET ended_at=?",java.time.LocalDateTime.now(java.time.ZoneOffset.UTC).minusDays(31));application.getBean(com.example.controller.RecordingController.class).expire();
        assertNull(jdbc.queryForObject("SELECT manifest_json FROM recording_analysis",String.class));assertFalse(java.nio.file.Files.exists(java.nio.file.Path.of(recordingRoot,value.path("file").asText().replace(".mp4",".analysis.json"))));
        String path="/camera/1/recordings/"+value.path("id").asText()+"/analysis";mvc.perform(get(path).servletPath(path).session(login("operator"))).andExpect(status().isGone());
    }
    @Test void p1ConcurrentCameraNamesAreUniqueAndNewDevicesAreUnverified()throws Exception{
        var pool=Executors.newFixedThreadPool(2);
        try{
            var barrier=new CyclicBarrier(2);
            var calls=List.<Callable<Boolean>>of(()->{barrier.await();var dto=new com.example.dto.camera.CameraCreateDTO();dto.setName("duplicate camera");dto.setLocation("test");dto.setRtspUrl("rtsp://127.0.0.1:8554/test");try{cameras.createCamera(dto);return true;}catch(org.springframework.dao.DuplicateKeyException | com.example.common.exception.BusinessException expected){return false;}},()->{barrier.await();var dto=new com.example.dto.camera.CameraCreateDTO();dto.setName("duplicate camera");dto.setLocation("test");dto.setRtspUrl("rtsp://127.0.0.1:8554/test");try{cameras.createCamera(dto);return true;}catch(org.springframework.dao.DuplicateKeyException | com.example.common.exception.BusinessException expected){return false;}});
            int successes=0;for(var response:pool.invokeAll(calls))if(response.get())successes++;
            assertEquals(1,successes);assertEquals(3,jdbc.queryForObject("SELECT status FROM camera WHERE name='duplicate camera'",Integer.class));
        }finally{pool.shutdownNow();}
    }

}
