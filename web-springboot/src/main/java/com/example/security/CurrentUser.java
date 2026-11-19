package com.example.security;
import com.example.common.exception.BusinessException;
import org.springframework.security.core.context.SecurityContextHolder;
public final class CurrentUser {
    private CurrentUser(){}
    public static SessionUser principal(){
        var auth=SecurityContextHolder.getContext().getAuthentication();
        if(auth==null || !(auth.getPrincipal() instanceof SessionUser user))throw new BusinessException(401,"请先登录");
        return user;
    }
    public static boolean admin(){
        var auth=SecurityContextHolder.getContext().getAuthentication();
        return auth!=null && auth.getAuthorities().stream().anyMatch(a->a.getAuthority().equals("ROLE_ADMIN"));
    }
}
