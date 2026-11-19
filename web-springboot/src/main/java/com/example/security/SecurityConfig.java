package com.example.security;

import com.example.common.Result;
import com.example.mapper.UserMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.*;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

@Configuration @EnableMethodSecurity @RequiredArgsConstructor
public class SecurityConfig {
    private final ObjectMapper mapper;
    private final UserMapper users;
    private final JdbcTemplate jdbc;
    @Value("${railway.preview-service-key:}") private String serviceKey;
    @Value("${railway.evidence-service-key:}") private String evidenceKey;
    @Value("${railway.worker-id:detector-1}") private String workerId;
    @Bean @Order(0) SecurityFilterChain evidence(HttpSecurity http)throws Exception{
        return http.securityMatcher("/_evidence/**").csrf(c->c.disable())
            .sessionManagement(s->s.sessionCreationPolicy(org.springframework.security.config.http.SessionCreationPolicy.STATELESS))
            .addFilterBefore(new OncePerRequestFilter(){
                protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException{
                    String header=req.getHeader("Authorization");
                    if(evidenceKey.length()<32 || req.getHeader("Origin")!=null || !workerId.equals(req.getHeader("X-Worker-Id")) || header==null ||
                        !MessageDigest.isEqual(("Bearer "+evidenceKey).getBytes(StandardCharsets.UTF_8),header.getBytes(StandardCharsets.UTF_8))){error(res,401,"证据服务身份无效");return;}
                    var context=SecurityContextHolder.createEmptyContext();context.setAuthentication(new UsernamePasswordAuthenticationToken(workerId,null,List.of(new SimpleGrantedAuthority("ROLE_EVIDENCE"))));
                    SecurityContextHolder.setContext(context);chain.doFilter(req,res);
                }
            },AnonymousAuthenticationFilter.class)
            .authorizeHttpRequests(a->a.anyRequest().hasRole("EVIDENCE"))
            .exceptionHandling(e->e.authenticationEntryPoint((q,r,x)->error(r,401,"证据服务身份无效"))).build();
    }
    @Bean PasswordEncoder passwordEncoder(){return new BCryptPasswordEncoder(12);}
    @Bean org.springframework.security.core.userdetails.UserDetailsService noDefaultAccount(){
        return username->{throw new org.springframework.security.core.userdetails.UsernameNotFoundException("Use the application login endpoint");};
    }
    @Bean HttpSessionSecurityContextRepository securityContextRepository(){return new HttpSessionSecurityContextRepository();}
    @Bean CsrfTokenRepository csrfRepository(){return new HttpSessionCsrfTokenRepository();}
    private void error(HttpServletResponse response,int code,String message)throws IOException{
        response.setStatus(code);response.setContentType("application/json;charset=UTF-8");
        mapper.writeValue(response.getOutputStream(),Result.error(code,message));
    }
    @Bean @Order(1) SecurityFilterChain internal(HttpSecurity http)throws Exception{
        return http.securityMatcher("/_internal/**").csrf(c->c.disable())
            .sessionManagement(s->s.sessionCreationPolicy(org.springframework.security.config.http.SessionCreationPolicy.STATELESS))
            .addFilterBefore(new OncePerRequestFilter(){
                protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException{
                    String header=req.getHeader("Authorization");
                    if(serviceKey.length()<32 || req.getHeader("Origin")!=null || header==null ||
                       !MessageDigest.isEqual(("Bearer "+serviceKey).getBytes(StandardCharsets.UTF_8),header.getBytes(StandardCharsets.UTF_8))){error(res,401,"服务身份无效");return;}
                    var context=SecurityContextHolder.createEmptyContext();
                    context.setAuthentication(new UsernamePasswordAuthenticationToken("preview-service",null,List.of(new SimpleGrantedAuthority("ROLE_SERVICE"))));
                    SecurityContextHolder.setContext(context);chain.doFilter(req,res);
                }
            },AnonymousAuthenticationFilter.class)
            .authorizeHttpRequests(a->a.anyRequest().hasRole("SERVICE"))
            .exceptionHandling(e->e.authenticationEntryPoint((q,r,x)->error(r,401,"服务身份无效"))).build();
    }
    @Bean @Order(2) SecurityFilterChain browser(HttpSecurity http,CsrfTokenRepository csrfRepository)throws Exception{
        return http.csrf(c->c.csrfTokenRepository(csrfRepository).csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler()))
            .securityContext(s->s.securityContextRepository(securityContextRepository()))
            .authorizeHttpRequests(a->a.requestMatchers("/user/login","/auth/csrf","/health/live","/health/ready","/error").permitAll().anyRequest().authenticated())
            .addFilterBefore(new OncePerRequestFilter(){
                protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException{
                    var auth=SecurityContextHolder.getContext().getAuthentication();
                    if(auth!=null && auth.getPrincipal() instanceof SessionUser principal){
                        var user=users.selectById(principal.id());
                        if(user==null || user.getStatus()!=1 || user.getSecurityVersion()!=principal.version()){
                            var session=req.getSession(false);
                            if(session!=null){jdbc.update("DELETE FROM preview_grant WHERE session_id=?",session.getId());session.invalidate();}
                            SecurityContextHolder.clearContext();error(res,401,"登录状态已失效");return;
                        }
                        String path=req.getServletPath();
                        if(Boolean.TRUE.equals(user.getPasswordChangeRequired()) && !List.of("/user/current","/user/password","/user/logout","/auth/csrf").contains(path)){
                            error(res,403,"请先修改临时或迁移口令");return;
                        }
                    }
                    chain.doFilter(req,res);
                }
            },AnonymousAuthenticationFilter.class)
            .logout(l->l.logoutUrl("/user/logout").addLogoutHandler((req,res,auth)->{
                var session=req.getSession(false);if(session!=null)jdbc.update("DELETE FROM preview_grant WHERE session_id=?",session.getId());
            }).logoutSuccessHandler((req,res,auth)->{res.setContentType("application/json;charset=UTF-8");mapper.writeValue(res.getOutputStream(),Result.success());}))
            .exceptionHandling(e->e.authenticationEntryPoint((q,r,x)->error(r,401,"请先登录"))
                                  .accessDeniedHandler((q,r,x)->error(r,403,"没有权限或 CSRF 令牌无效")))
            .requestCache(c->c.disable()).formLogin(c->c.disable()).httpBasic(c->c.disable()).build();
    }
}
