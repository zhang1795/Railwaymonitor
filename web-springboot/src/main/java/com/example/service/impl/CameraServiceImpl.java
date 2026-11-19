package com.example.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.example.common.exception.BusinessException;
import com.example.dto.camera.CameraCreateDTO;
import com.example.dto.camera.CameraQueryDTO;
import com.example.dto.camera.CameraUpdateDTO;
import com.example.entity.Camera;
import com.example.mapper.CameraMapper;
import com.example.service.CameraService;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 摄像头设备服务实现类
 */
@Service
@lombok.RequiredArgsConstructor
public class CameraServiceImpl extends ServiceImpl<CameraMapper, Camera> implements CameraService {
    private final com.example.detection.CameraRiskRules riskRules;
    private final com.example.detection.SourcePolicy sources;
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createCamera(CameraCreateDTO dto) {
        if(dto.getName()==null || dto.getName().isBlank())throw new BusinessException(400,"设备名称不能为空");
        dto.setName(dto.getName().trim());
        // 校验设备名称是否存在
        if (lambdaQuery().eq(Camera::getName, dto.getName()).count() > 0) {
            throw new BusinessException("设备名称已存在");
        }

        // 创建设备
        sources.validate(dto.getRtspUrl());
        Camera camera = BeanUtil.copyProperties(dto, Camera.class);
        // Registration is not a successful reachability/decoder observation.
        camera.setStatus(3);

        // 保存设备
        save(camera);
        riskRules.initialize(camera.getId());
        return camera.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateCamera(CameraUpdateDTO dto) {
        if(dto.getName()==null || dto.getName().isBlank())throw new BusinessException(400,"设备名称不能为空");
        dto.setName(dto.getName().trim());
        jdbc.queryForList("SELECT id FROM camera WHERE id=? FOR UPDATE", dto.getId());
        // 查询设备
        Camera camera = getById(dto.getId());
        if (camera == null) {
            throw new BusinessException("设备不存在");
        }

        // 校验设备名称是否存在
        if (!camera.getName().equals(dto.getName()) &&
            lambdaQuery().eq(Camera::getName, dto.getName()).count() > 0) {
            throw new BusinessException("设备名称已存在");
        }

        // Empty URL on edit means preserve the secret server-side source.
        if (dto.getRtspUrl() == null || dto.getRtspUrl().isBlank()) dto.setRtspUrl(camera.getRtspUrl());
        if (!camera.getRtspUrl().equals(dto.getRtspUrl()) && jdbc.queryForObject(
                "SELECT COUNT(*) FROM monitoring_task WHERE camera_id=? AND enabled=TRUE", Integer.class, camera.getId())>0)
            throw new BusinessException(409,"请先停用后台检测再修改视频源");
        sources.validate(dto.getRtspUrl());
        if (dto.getStatus() != null && (dto.getStatus()<0 || dto.getStatus()>3)) throw new BusinessException(400,"状态无效");
        BeanUtil.copyProperties(dto, camera, cn.hutool.core.bean.copier.CopyOptions.create().ignoreNullValue());

        // 如果状态不是故障，清空故障类型
        if (camera.getStatus() != 2) {
            camera.setFaultType(null);
        }

        updateById(camera);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteCamera(Long id) {
        jdbc.queryForList("SELECT id FROM camera WHERE id=? FOR UPDATE", id);
        // 查询设备
        Camera camera = getById(id);
        if (camera == null) {
            throw new BusinessException("设备不存在");
        }

        if (jdbc.queryForObject("SELECT COUNT(*) FROM monitoring_task WHERE camera_id=? AND enabled=TRUE", Integer.class,id)>0) throw new BusinessException(409,"请先停用后台检测再删除设备");
        removeById(id);
    }

    @Override
    public IPage<Camera> getCameraPage(CameraQueryDTO dto) {
        // 构建查询条件
        LambdaQueryWrapper<Camera> wrapper = new LambdaQueryWrapper<Camera>()
                .like(StrUtil.isNotBlank(dto.getName()), Camera::getName, dto.getName())
                .like(StrUtil.isNotBlank(dto.getLocation()), Camera::getLocation, dto.getLocation())
                .like(StrUtil.isNotBlank(dto.getIpAddress()), Camera::getIpAddress, dto.getIpAddress())
                .eq(dto.getStatus() != null, Camera::getStatus, dto.getStatus());

        // 执行分页查询
        var result=page(new Page<Camera>(Math.max(1,dto.getCurrent()), Math.max(1,Math.min(100,dto.getSize()))), wrapper);
        riskRules.addSummaries(result.getRecords());
        return result;
    }

    @Override
    public Camera getCameraById(Long id) {
        // 查询设备
        Camera camera = getById(id);
        if (camera == null) {
            throw new BusinessException("设备不存在");
        }
        return camera;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateCameraStatus(Long id, Integer status) {
        if (status==null || status<0 || status>3) throw new BusinessException(400,"状态无效");
        // 查询摄像头
        Camera camera = getById(id);
        if (camera == null) {
            throw new BusinessException("摄像头不存在");
        }
        // 更新状态
        camera.setStatus(status);
        updateById(camera);
    }
}
