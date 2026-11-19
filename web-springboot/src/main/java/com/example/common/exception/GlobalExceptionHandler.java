package com.example.common.exception;

import lombok.extern.slf4j.Slf4j;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;

import com.example.common.Result;

/**
 * 全局异常处理器
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /**
     * 处理参数校验异常
     */
    @ExceptionHandler(BindException.class)
    public ResponseEntity<Result<Void>> handleBindException(BindException e) {
        log.warn("参数校验失败: {}", e.getBindingResult().getObjectName());
        return ResponseEntity.badRequest().body(Result.error(400, e.getBindingResult().getAllErrors().get(0).getDefaultMessage()));
    }

    /**
     * 处理业务异常
     */
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<Result<Void>> handleBusinessException(BusinessException e) {
        log.warn("业务请求被拒绝: code={}",e.getCode());
        int status = e.getCode() >= 400 && e.getCode() <= 599 ? e.getCode() : 500;
        return ResponseEntity.status(status).body(Result.error(e.getCode(), e.getMessage()));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<Result<Void>> accessDenied(AccessDeniedException e) {
        return ResponseEntity.status(403).body(Result.error(403,"没有权限"));
    }
    @ExceptionHandler(org.springframework.dao.DuplicateKeyException.class)
    public ResponseEntity<Result<Void>> duplicate(org.springframework.dao.DuplicateKeyException e){return ResponseEntity.status(409).body(Result.error(409,"记录名称或业务键已存在，请刷新后核对"));}
    @ExceptionHandler(org.springframework.dao.DataAccessException.class)
    public ResponseEntity<Result<Void>> dataUnavailable(org.springframework.dao.DataAccessException e){return ResponseEntity.status(503).body(Result.error(503,"数据服务暂不可用，请稍后重试"));}

    /**
     * 处理其他异常
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Result<Void>> handleException(Exception e) {
        log.error("系统异常", e);
        String errorMsg = "系统异常，请联系管理员";
    return ResponseEntity.internalServerError().body(Result.error(errorMsg));
}
}
