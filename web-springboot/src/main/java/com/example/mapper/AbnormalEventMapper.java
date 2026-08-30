package com.example.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.entity.AbnormalEvent;

import org.apache.ibatis.annotations.Mapper;

/**
 * 异常事件记录Mapper接口
 */
@Mapper
public interface AbnormalEventMapper extends BaseMapper<AbnormalEvent> {
} 