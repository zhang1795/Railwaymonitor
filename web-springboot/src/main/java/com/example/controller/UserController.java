package com.example.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.example.common.Result;
import com.example.dto.user.*;
import com.example.entity.User;
import com.example.service.UserService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 用户控制器
 */
@Tag(name = "用户管理", description = "用户管理相关接口")
@RestController
@RequestMapping("/user")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    /**
     * 用户登录
     */
    @Operation(summary = "用户登录", description = "用户登录接口")
    @PostMapping("/login")
    public Result<UserLoginVO> login(@RequestBody @Valid UserLoginDTO dto) {
        return Result.success(userService.login(dto));
    }

    /**
     * 用户注册
     */
    @Operation(summary = "用户注册", description = "用户注册接口")
    @PostMapping("/register")
    public Result<Void> register(@RequestBody @Valid UserRegisterDTO dto) {
        userService.register(dto);
        return Result.success();
    }

    /**
     * 修改密码
     */
    @Operation(summary = "修改密码", description = "修改用户密码接口")
    @PostMapping("/password")
    public Result<Void> updatePassword(@RequestBody @Valid UserPasswordDTO dto) {
        userService.updatePassword(dto);
        return Result.success();
    }

    /**
     * 更新用户信息
     */
    @Operation(summary = "更新用户信息", description = "更新用户基本信息接口")
    @PutMapping
    public Result<Void> updateUser(@RequestBody @Valid UserUpdateDTO dto) {
        userService.updateUser(dto);
        return Result.success();
    }

    /**
     * 分页查询用户列表
     */
    @Operation(summary = "分页查询用户列表", description = "分页查询用户列表接口")
    @GetMapping("/page")
    public Result<IPage<User>> getUserPage(UserQueryDTO dto) {
        return Result.success(userService.getUserPage(dto));
    }

    /**
     * 获取当前登录用户信息
     */
    @Operation(summary = "获取当前用户信息", description = "获取当前登录用户信息接口")
    @GetMapping("/current")
    public Result<UserLoginVO> getCurrentUser() {
        return Result.success(userService.getCurrentUser());
    }

    /**
     * 获取用户详情
     */
    @Operation(summary = "获取用户详情", description = "根据用户ID获取用户详情")
    @GetMapping("/{id}")
    public Result<User> getUserInfo(@PathVariable Long id) {
        return Result.success(userService.getById(id));
    }

    /**
     * 删除用户
     */
    @Operation(summary = "删除用户", description = "删除用户接口")
    @DeleteMapping("/{id}")
    public Result<Void> deleteUser(@PathVariable Long id) {
        userService.removeById(id);
        return Result.success();
    }

    /**
     * 退出登录
     */
    @Operation(summary = "退出登录", description = "用户退出登录接口")
    @PostMapping("/logout")
    public Result<Void> logout() {
        userService.logout();
        return Result.success();
    }

    /**
     * 重置密码
     */
    @Operation(summary = "重置密码", description = "管理员重置用户密码为默认密码")
    @PutMapping("/{id}/reset-password")
    public Result<Void> resetPassword(@PathVariable("id") Long id) {
        userService.resetPassword(id);
        return Result.success();
    }
} 