package com.example.dto.Abnormal;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
@Schema(description = "异常事件更新DTO")
public class AbnormalEventUpdateDTO {

    @NotNull(message = "事件ID不能为空")
    @Schema(description = "事件ID")
    private Long id;

    @Schema(description = "摄像头ID")
    private Long cameraId;

    @Schema(description = "位置")
    private String location;

    @Schema(description = "异常等级：0-无异常，1-可疑异常，2-轻微异常，3-中等异常，4-严重异常，5-特别严重")
    private Integer level;

    @Schema(description = "图片URL")
    private String imageUrl;

    @Schema(description = "事件描述")
    private String description;
} 