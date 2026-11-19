package com.example.dto.camera;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 摄像头设备创建DTO
 */
@Data
public class CameraCreateDTO {
    /**
     * 设备名称
     */
    @NotBlank(message = "设备名称不能为空")
    @jakarta.validation.constraints.Size(max=100)
    private String name;

    /**
     * 安装位置
     */
    @NotBlank(message = "安装位置不能为空")
    @jakarta.validation.constraints.Size(max=200)
    private String location;

    /**
     * IP地址
     */
    @jakarta.validation.constraints.Size(max=50)
    private String ipAddress;

    /**
     * RTSP地址
     */
    @jakarta.validation.constraints.Size(max=1000)
    @lombok.ToString.Exclude
    private String rtspUrl;

    /**
     * 经度
     */
    @jakarta.validation.constraints.DecimalMin("-180") @jakarta.validation.constraints.DecimalMax("180")
    private Double longitude;  // 新增字段

    /**
     * 纬度
     */
    @jakarta.validation.constraints.DecimalMin("-90") @jakarta.validation.constraints.DecimalMax("90")
    private Double latitude;   // 新增字段
}
 