package com.example.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.entity.Camera;

import org.apache.ibatis.annotations.Mapper;

/**
 * 摄像头设备Mapper接口
 */
@Mapper
public interface CameraMapper extends BaseMapper<Camera> {
} 