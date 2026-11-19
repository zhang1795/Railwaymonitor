package com.example.detection;

import com.fasterxml.jackson.databind.*;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** Bounded HTTP delivery. SMS acceptance and carrier delivery are different states. */
@Component @RequiredArgsConstructor
public class NotificationTransport {
    private final ObjectMapper json;
    @Value("${railway.notify.webhook-url:}") private String webhookUrl;
    @Value("${railway.notify.webhook-key:}") private String webhookKey;
    @Value("${railway.notify.allow-loopback:false}") private boolean loopback;
    @Value("${railway.notify.sms-access-key:}") private String accessKey;
    @Value("${railway.notify.sms-secret:}") private String secret;
    @Value("${railway.notify.sms-sign:}") private String sign;
    @Value("${railway.notify.sms-template:}") private String template;
    @Value("${railway.notify.sms-recipients:}") private String recipients;
    @Value("${railway.notify.sms-template-params:{}}") private String templateParams;
    private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).followRedirects(HttpClient.Redirect.NEVER).build();
    public record Outcome(String status,String providerId,String error){}
    public boolean webhookConfigured(){
        try{var uri=URI.create(webhookUrl);return webhookKey.length()>=32 && uri.getUserInfo()==null && uri.getFragment()==null && (uri.getScheme().equals("https") || loopback && uri.getScheme().equals("http") && Set.of("127.0.0.1","localhost","::1").contains(uri.getHost()));}catch(Exception e){return false;}
    }
    public List<String> phones(){return Arrays.stream(recipients.split(",")).map(String::trim).filter(value->value.matches("(?:\\+?86)?1[3-9][0-9]{9}")).distinct().limit(100).toList();}
    public boolean smsConfigured(){return !accessKey.isBlank() && !secret.isBlank() && !sign.isBlank() && template.matches("SMS_[A-Za-z0-9]+") && !phones().isEmpty();}
    public static String sha(byte[] body)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));}
    public static String hmac(String key,String value)throws Exception{var mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8),"HmacSHA256"));return HexFormat.of().formatHex(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));}
    public static String encode(String value){return URLEncoder.encode(value,StandardCharsets.UTF_8).replace("+","%20").replace("*","%2A").replace("%7E","~");}
    public static String query(Map<String,String> params){return new TreeMap<>(params).entrySet().stream().map(entry->encode(entry.getKey())+"="+encode(entry.getValue())).collect(java.util.stream.Collectors.joining("&"));}
    /** Alibaba Cloud ACS3-HMAC-SHA256, validated against the official fixed vector. */
    public static Map<String,String> signedHeaders(String key,String secret,String host,String action,String version,String date,String nonce,String query)throws Exception{
        var headers=new TreeMap<String,String>();headers.put("host",host);headers.put("x-acs-action",action);headers.put("x-acs-version",version);headers.put("x-acs-date",date);headers.put("x-acs-signature-nonce",nonce);headers.put("x-acs-content-sha256",sha(new byte[0]));
        String canonical=headers.entrySet().stream().map(e->e.getKey()+":"+e.getValue().trim()+"\n").collect(java.util.stream.Collectors.joining());
        String names=String.join(";",headers.keySet());
        String request="POST\n/\n"+query+"\n"+canonical+"\n"+names+"\n"+headers.get("x-acs-content-sha256");
        headers.put("Authorization","ACS3-HMAC-SHA256 Credential="+key+",SignedHeaders="+names+",Signature="+hmac(secret,"ACS3-HMAC-SHA256\n"+sha(request.getBytes(StandardCharsets.UTF_8))));return headers;
    }
    private byte[] response(HttpRequest request)throws Exception{
        // A limiting subscriber bounds body memory, and a total deadline also
        // covers a peer that sends headers then trickles/never finishes a body.
        var future=client.sendAsync(request,info->new LimitedBody());
        try{
            var result=future.get(6,TimeUnit.SECONDS);
            if(result.statusCode()<200 || result.statusCode()>=300)throw new ProviderHttp(result.statusCode());
            return result.body();
        }catch(Exception e){future.cancel(true);throw e;}
    }
    private static final class ProviderHttp extends Exception {final int status;ProviderHttp(int status){this.status=status;}}
    private static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
        final CompletableFuture<byte[]> body=new CompletableFuture<>();final java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();java.util.concurrent.Flow.Subscription subscription;
        public CompletionStage<byte[]> getBody(){return body;}
        public void onSubscribe(java.util.concurrent.Flow.Subscription value){subscription=value;value.request(1);}
        public void onNext(List<java.nio.ByteBuffer> buffers){
            for(var buffer:buffers){if(bytes.size()+buffer.remaining()>8192){subscription.cancel();body.completeExceptionally(new IllegalStateException("provider_response_too_large"));return;}byte[] chunk=new byte[buffer.remaining()];buffer.get(chunk);bytes.writeBytes(chunk);}subscription.request(1);
        }
        public void onError(Throwable error){body.completeExceptionally(error);}public void onComplete(){body.complete(bytes.toByteArray());}
    }
    private JsonNode aliyun(String action,Map<String,String> params)throws Exception{
        String qs=query(params);var headers=signedHeaders(accessKey,secret,"dysmsapi.aliyuncs.com",action,"2017-05-25",Instant.now().truncatedTo(java.time.temporal.ChronoUnit.SECONDS).toString(),UUID.randomUUID().toString().replace("-",""),qs);
        var builder=HttpRequest.newBuilder(URI.create("https://dysmsapi.aliyuncs.com/?"+qs)).timeout(Duration.ofSeconds(5)).POST(HttpRequest.BodyPublishers.noBody());
        headers.forEach((key,value)->{if(!key.equals("host"))builder.header(key,value);});return json.readTree(response(builder.build()));
    }
    public Outcome deliver(Map<String,Object> delivery){
        boolean sms="SMS".equals(delivery.get("channel")),poll="POLL".equals(delivery.get("phase"));
        try{
            var payload=json.readTree((String)delivery.get("payload"));
            if(!sms){
                if(!webhookConfigured())return new Outcome("NOT_CONFIGURED",null,"");
                byte[] body=((String)delivery.get("payload")).getBytes(StandardCharsets.UTF_8);String timestamp=Instant.now().toString(),id=(String)delivery.get("id");
                var request=HttpRequest.newBuilder(URI.create(webhookUrl)).timeout(Duration.ofSeconds(5)).header("Content-Type","application/json").header("X-Notification-Id",id).header("X-Notification-Time",timestamp).header("X-Notification-Signature",hmac(webhookKey,id+"\n"+timestamp+"\n"+sha(body))).POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
                response(request);return new Outcome("ACKNOWLEDGED",null,"");
            }
            if(!smsConfigured())return new Outcome("NOT_CONFIGURED",null,"");
            var params=new LinkedHashMap<String,String>();JsonNode reply;
            if(poll){
                var created=delivery.get("sent_at")==null?delivery.get("created_at"):delivery.get("sent_at");var createdAt=created instanceof java.sql.Timestamp t?t.toLocalDateTime():(LocalDateTime)created;
                params.put("PhoneNumber",(String)delivery.get("target"));params.put("BizId",(String)delivery.get("provider_id"));params.put("SendDate",createdAt.atZone(ZoneOffset.UTC).withZoneSameInstant(ZoneId.of("Asia/Shanghai")).toLocalDate().toString().replace("-",""));params.put("PageSize","50");params.put("CurrentPage","1");
                reply=aliyun("QuerySendDetails",params);
                if(!reply.path("Code").asText().equals("OK"))return new Outcome("ACCEPTED",(String)delivery.get("provider_id"),"receipt_query_rejected");
                for(var row:reply.path("SmsSendDetailDTOs").path("SmsSendDetailDTO")){
                    int state=row.path("SendStatus").asInt();
                    if(state==3)return new Outcome("DELIVERED",(String)delivery.get("provider_id"),"");
                    if(state==2)return new Outcome("FAILED",(String)delivery.get("provider_id"),"carrier_delivery_failed");
                }
                return new Outcome("ACCEPTED",(String)delivery.get("provider_id"),"");
            }
            var variables=json.readTree(templateParams);var resolved=json.createObjectNode();
            if(!variables.isObject())return new Outcome("FAILED",null,"invalid_template_variables");
            variables.fields().forEachRemaining(entry->{String text=entry.getValue().asText();for(String key:List.of("type","level","time","kind","alarmId","cameraId"))text=text.replace("${"+key+"}",payload.path(key).asText());resolved.put(entry.getKey(),text);});
            params.put("PhoneNumbers",(String)delivery.get("target"));params.put("SignName",sign);params.put("TemplateCode",template);params.put("TemplateParam",json.writeValueAsString(resolved));params.put("OutId",(String)delivery.get("id"));
            reply=aliyun("SendSms",params);
            if(!reply.path("Code").asText().equals("OK")){
                String error=reply.path("Code").asText("provider_rejected").replaceAll("[^A-Za-z0-9_.-]","");
                return new Outcome("FAILED",null,error.substring(0,Math.min(120,error.length())));
            }
            if(reply.path("BizId").asText().isBlank())return new Outcome("UNKNOWN",null,"accepted_without_receipt_identifier");
            return new Outcome("ACCEPTED",reply.path("BizId").asText(),"");
        }catch(ProviderHttp e){return new Outcome(poll?"ACCEPTED":e.status==429?"RETRY":sms && e.status>=500?"UNKNOWN":e.status>=500?"RETRY":"FAILED",(String)delivery.get("provider_id"),"provider_http_"+e.status);}
        catch(Exception e){return new Outcome(poll?"ACCEPTED":sms?"UNKNOWN":"RETRY",(String)delivery.get("provider_id"),"transport_result_unconfirmed");}
    }
}
