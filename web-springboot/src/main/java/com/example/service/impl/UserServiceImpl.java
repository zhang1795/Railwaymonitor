package com.example.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.crypto.SecureUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.example.common.exception.BusinessException;
import com.example.dto.user.*;
import com.example.entity.User;
import com.example.mapper.UserMapper;
import com.example.service.UserService;
import com.example.security.*;
import jakarta.servlet.http.*;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.*;

@Service @RequiredArgsConstructor
public class UserServiceImpl extends ServiceImpl<UserMapper,User> implements UserService {
    private final HttpServletRequest request;
    private final HttpServletResponse response;
    private final PasswordEncoder passwords;
    private final HttpSessionSecurityContextRepository contexts;
    private final CsrfTokenRepository csrf;
    private final JdbcTemplate jdbc;
    @Value("${railway.allow-legacy-md5-login:false}") private boolean legacy;
    private final LinkedHashMap<String,long[]> attempts=new LinkedHashMap<>();
    private void checkPassword(String value){
        if(value==null || value.length()<12 || value.getBytes(StandardCharsets.UTF_8).length>72)
            throw new BusinessException(400,"口令至少 12 个字符，UTF-8 长度最多 72 字节");
    }
    private boolean matches(String raw,String stored){
        if(stored==null || raw==null || raw.getBytes(StandardCharsets.UTF_8).length>72)return false;
        if(stored.startsWith("$2"))return passwords.matches(raw,stored);
        return legacy && stored.matches("[a-fA-F0-9]{32}") && SecureUtil.md5(raw).equalsIgnoreCase(stored);
    }
    @Override public UserLoginVO login(UserLoginDTO dto){
        String key=request.getRemoteAddr();long now=System.nanoTime();
        synchronized(attempts){
            attempts.entrySet().removeIf(e->now-e.getValue()[0]>300_000_000_000L);
            long[] attempt=attempts.computeIfAbsent(key,k->new long[]{now,0});
            if(attempt[1]>=8)throw new BusinessException(429,"登录尝试过多，请稍后重试");
            attempt[1]++;while(attempts.size()>10000)attempts.remove(attempts.keySet().iterator().next());
        }
        User user=lambdaQuery().eq(User::getUsername,dto.getUsername()).one();
        if(user==null || user.getStatus()!=1 || !matches(dto.getPassword(),user.getPassword()))
            throw new BusinessException(401,"用户名或口令无效");
        if(!user.getPassword().startsWith("$2")){
            if(jdbc.update("UPDATE `user` SET password=?,password_change_required=TRUE WHERE id=? AND security_version=? AND password=? AND status=1",
                passwords.encode(dto.getPassword()),user.getId(),user.getSecurityVersion(),user.getPassword())!=1)
                throw new BusinessException(401,"登录状态已变更，请重试");
            user.setPasswordChangeRequired(true);
        }
        synchronized(attempts){attempts.remove(key);}
        request.getSession();request.changeSessionId();csrf.saveToken(null,request,response);
        var context=SecurityContextHolder.createEmptyContext();
        context.setAuthentication(new UsernamePasswordAuthenticationToken(new SessionUser(user.getId(),user.getSecurityVersion()),null,
            List.of(new SimpleGrantedAuthority(user.getRole()==1?"ROLE_ADMIN":"ROLE_USER"))));
        SecurityContextHolder.setContext(context);contexts.saveContext(context,request,response);
        return BeanUtil.copyProperties(user,UserLoginVO.class);
    }
    @Override public void register(UserRegisterDTO dto){
        checkPassword(dto.getPassword());
        if(lambdaQuery().eq(User::getUsername,dto.getUsername()).count()>0)throw new BusinessException(409,"用户名已存在");
        User user=BeanUtil.copyProperties(dto,User.class);user.setPassword(passwords.encode(dto.getPassword()));
        user.setRole(dto.getRole()==null?0:dto.getRole());user.setStatus(dto.getStatus()==null?1:dto.getStatus());
        user.setSecurityVersion(0L);user.setPasswordChangeRequired(true);save(user);
    }
    @Override @Transactional public void updatePassword(UserPasswordDTO dto){
        long id=CurrentUser.principal().id();
        if(dto.getId()!=id)throw new BusinessException(403,"只能修改本人登录口令");
        checkPassword(dto.getNewPassword());lockAccountChanges();User user=getById(id);
        if(!matches(dto.getOldPassword(),user.getPassword()))throw new BusinessException(400,"原口令无效");
        if(dto.getNewPassword().equals(dto.getOldPassword()))throw new BusinessException(400,"新口令必须与原口令不同");
        user.setPassword(passwords.encode(dto.getNewPassword()));user.setPasswordChangeRequired(false);
        user.setSecurityVersion(user.getSecurityVersion()+1);updateById(user);
        jdbc.update("DELETE FROM preview_grant WHERE user_id=?",id);
    }
    private void protectLastAdmin(User user,Integer role,Integer status){
        jdbc.queryForList("SELECT id FROM `user` WHERE role=1 ORDER BY id FOR UPDATE");
        if(user.getRole()==1 && user.getStatus()==1 &&
            ((role!=null && role!=1)||(status!=null && status!=1)) &&
            lambdaQuery().eq(User::getRole,1).eq(User::getStatus,1).count()<=1)
            throw new BusinessException(409,"必须保留至少一个有效管理员");
    }
    private void lockAccountChanges(){
        // Rare administrative writes serialize in a consistent lock order.
        // Prevent stale entity updates from restoring roles or reusing a
        // security version during concurrent resets/edits.
        jdbc.queryForList("SELECT id FROM `user` ORDER BY id FOR UPDATE");
    }
    @Override @Transactional public void updateUser(UserUpdateDTO dto){
        if(!CurrentUser.admin() && (dto.getId()!=CurrentUser.principal().id() || dto.getRole()!=null || dto.getStatus()!=null))
            throw new BusinessException(403,"不能修改他人资料或授权字段");
        lockAccountChanges();User user=getById(dto.getId());if(user==null)throw new BusinessException(404,"用户不存在");
        if(dto.getRole()!=null && dto.getRole()!=0 && dto.getRole()!=1 || dto.getStatus()!=null && dto.getStatus()!=0 && dto.getStatus()!=1)
            throw new BusinessException(400,"角色或状态无效");
        protectLastAdmin(user,dto.getRole(),dto.getStatus());
        if(dto.getRealName()!=null)user.setRealName(dto.getRealName());if(dto.getPhone()!=null)user.setPhone(dto.getPhone());
        if(dto.getEmail()!=null)user.setEmail(dto.getEmail());
        boolean changed=dto.getRole()!=null && !dto.getRole().equals(user.getRole()) || dto.getStatus()!=null && !dto.getStatus().equals(user.getStatus());
        if(dto.getRole()!=null)user.setRole(dto.getRole());if(dto.getStatus()!=null)user.setStatus(dto.getStatus());
        if(changed){user.setSecurityVersion(user.getSecurityVersion()+1);jdbc.update("DELETE FROM preview_grant WHERE user_id=?",user.getId());}
        updateById(user);
    }
    @Override public IPage<User> getUserPage(UserQueryDTO dto){
        return page(new Page<>(Math.max(1,dto.getCurrent()),Math.min(100,Math.max(1,dto.getSize()))),new LambdaQueryWrapper<User>()
            .like(StrUtil.isNotBlank(dto.getUsername()),User::getUsername,dto.getUsername())
            .like(StrUtil.isNotBlank(dto.getRealName()),User::getRealName,dto.getRealName())
            .eq(dto.getRole()!=null,User::getRole,dto.getRole()).eq(dto.getStatus()!=null,User::getStatus,dto.getStatus()));
    }
    @Override public UserLoginVO getCurrentUser(){return BeanUtil.copyProperties(getById(CurrentUser.principal().id()),UserLoginVO.class);}
    @Override public void logout(){var session=request.getSession(false);if(session!=null){jdbc.update("DELETE FROM preview_grant WHERE session_id=?",session.getId());session.invalidate();}SecurityContextHolder.clearContext();}
    @Override @Transactional public String resetPassword(Long id){
        lockAccountChanges();User user=getById(id);if(user==null)throw new BusinessException(404,"用户不存在");
        byte[] random=new byte[18];new SecureRandom().nextBytes(random);String temporary=Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        user.setPassword(passwords.encode(temporary));user.setPasswordChangeRequired(true);user.setSecurityVersion(user.getSecurityVersion()+1);updateById(user);
        jdbc.update("DELETE FROM preview_grant WHERE user_id=?",id);return temporary;
    }
    @Transactional public void deleteUser(Long id){
        lockAccountChanges();User user=getById(id);if(user==null)throw new BusinessException(404,"用户不存在");
        protectLastAdmin(user,0,0);jdbc.update("DELETE FROM preview_grant WHERE user_id=?",id);removeById(id);
    }
}
