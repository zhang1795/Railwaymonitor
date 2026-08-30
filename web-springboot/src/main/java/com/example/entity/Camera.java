package com.example.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 摄像头设备实体类
 */
@Data
@TableName("camera")
public class Camera {
    /**
     * 设备ID
     */
    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 设备名称
     */
    private String name;

    /**
     * 安装位置
     */
    private String location;

    /**
     * IP地址
     */
    private String ipAddress;

    /**
     * RTSP地址
     */
    private String rtspUrl;

    /**
     * 状态(0:离线 1:在线 2:故障)
     */
    private Integer status;

    /**
     * 故障类型
     */
    private String faultType;

    /**
     * 经度
     */
    private Double longitude;  // 新增字段

    /**
     * 纬度
     */
    private Double latitude;   // 新增字段

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
} 