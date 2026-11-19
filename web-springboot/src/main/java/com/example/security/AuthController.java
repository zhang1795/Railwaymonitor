package com.example.security;
import com.example.common.Result;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;
import java.util.Map;
@RestController
public class AuthController {
    @GetMapping("/auth/csrf") public Result<Map<String,String>> csrf(CsrfToken token){
        return Result.success(Map.of("headerName",token.getHeaderName(),"token",token.getToken()));
    }
}
