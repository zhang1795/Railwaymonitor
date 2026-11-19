package com.example.config;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.web.cors.*;
import org.springframework.web.filter.CorsFilter;
import java.util.*;
@Configuration
public class CorsConfig {
    @Bean public CorsFilter corsFilter(@Value("${railway.allowed-origins:}") String origins){
        var source=new UrlBasedCorsConfigurationSource();
        if(!origins.isBlank()){
            var config=new CorsConfiguration();config.setAllowedOrigins(Arrays.asList(origins.split(",")));
            config.setAllowedMethods(List.of("GET","POST","PUT","DELETE","OPTIONS"));
            config.setAllowedHeaders(List.of("Content-Type","X-CSRF-TOKEN"));config.setAllowCredentials(true);
            source.registerCorsConfiguration("/**",config);
        }
        return new CorsFilter(source);
    }
}
