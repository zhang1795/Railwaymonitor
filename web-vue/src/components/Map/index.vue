<template>
  <div class="map-wrapper">
    <div id="panel"></div>

    <div class="search-container">
      <el-input v-model="searchText" placeholder="请输入搜索关键字" id="searchInputId" />
    </div>

    <div id="amap"></div>

    <div class="draw-area">
      <div class="select">
        <div style="margin: 10px 0">
          <!-- <el-button @click="drawOther">绘制多边形</el-button> -->
          <el-button @click="drawRect">绘制矩形</el-button>
          <el-button @click="drawCircle">绘制圆形</el-button>
          <el-button @click="stopDrawAndClear()">清除</el-button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, reactive, nextTick } from "vue";
import AMapLoader from "@amap/amap-jsapi-loader";
// 引入摄像头相关API和类型
import { getCameraList } from '@/api/camera'
import type { Camera } from '@/types/camera'
import { ElMessage } from "element-plus";

// Props：控制是否显示定位/鹰眼/图层切换控件
const props = defineProps({
  showMapControls: {
    type: Boolean,
    default: true // 默认显示控件
  }
});

// 定义自定义事件，用于向父组件传递经纬度
const emit = defineEmits(['coordinate-select']);

const amapKey = import.meta.env.VITE_AMAP_KEY || ''
const amapSecurityCode = import.meta.env.VITE_AMAP_SECURITY_CODE || ''

window._AMapSecurityConfig = {
  securityJsCode: amapSecurityCode,
};
let map: any = null
let placeSearch,
  AMapObj: any,
  geocoder: { getAddress: (arg0: any, arg1: (status: any, result: any) => void) => void; }
let mouseTool: any = null
let circleId = 1
const auto = ref<any>(null)
let autoOptions = {
  input: 'searchInputId',
}
let searchText = ref('')
let currentMarker = ref<any>(null); // 保存当前点标记实例（用于自动清除上一个）


onMounted(() => {
  initMap();
});


// 初始化地图
async function initMap() {
  if (!amapKey || !amapSecurityCode) {
    ElMessage.warning('未配置高德地图密钥，地图功能暂不可用')
    return
  }

  await AMapLoader.load({
    key: amapKey,
    version: '2.0',
    plugins:
      ['AMap.ToolBar',
        'AMap.Scale',
        'AMap.Geolocation',
        'AMap.PlaceSearch',
        'AMap.Geocoder',
        'AMap.HawkEye',
        'AMap.MapType',
        'AMap.CircleEditor',
        'AMap.MouseTool',
        'AMap.AutoComplete',
        'AMap.PlaceSearch',
        'AMap.Driving'
      ],
  }).then(AMap => {
    AMapObj = AMap
    map = new AMap.Map('amap', {
      zoom: 12,
      resizeEnable: true,
      center: [103.841856, 36.053549],
      viewMode: "3D",
    })
    // 图层切换
    const mapType = new AMap.MapType()
    // 鹰眼
    const hawkEye = new AMap.HawkEye()
    // 缩放条
    const toolbar = new AMap.ToolBar({
      position: 'LT'
    })
    // 比例尺
    const scale = new AMap.Scale()
    // 定位
    const geolocation = new AMap.Geolocation({
      enableHighAccuracy: true,//是否使用高精度定位，默认:true
      timeout: 10000,          //超过10秒后停止定位，默认：无穷大
      maximumAge: 0,           //定位结果缓存0毫秒，默认：0
      convert: true,           //自动偏移坐标，偏移后的坐标为高德坐标，默认：true
      showButton: true,        //显示定位按钮，默认：true
      buttonPosition: 'LB',    //定位按钮停靠位置，默认：'LB'，左下角
      buttonOffset: new AMap.Pixel(10, 20),//定位按钮与设置的停靠位置的偏移量，默认：Pixel(10, 20)
      showMarker: true,        //定位成功后在定位到的位置显示点标记，默认：true
      showCircle: true,        //定位成功后用圆圈表示定位精度范围，默认：true
      panToLocation: true,     //定位成功后将定位到的位置作为地图中心点，默认：true
      zoomToAccuracy: true      //定位成功后调整地图视野范围使定位位置及精度范围视野内可见，默认：false
    });
    geocoder = new AMap.Geocoder({
      city: '全国',
    });

    // 根据Props决定是否添加 定位/鹰眼/图层切换 控件
    if (props.showMapControls) {
      map.addControl(geolocation)  // 定位控件
      map.addControl(hawkEye)      // 鹰眼控件
      map.addControl(mapType)      // 图层切换控件
    }

    // 缩放条、比例尺：始终保留（若需隐藏，也可包进上面的if）
    map.addControl(toolbar)  // 放大缩小组件
    map.addControl(scale)    // 比例尺

    // POI搜索
    poiSearch();

    // 为地图绑定点击事件
    bindEvent()

    // 覆盖物
    mouseTool = new AMap.MouseTool(map); //创建鼠标工具插件实例

    // 获取摄像头数据
    getCameraData()
  }
  );
}


// 搜索（在新增对话框中好像因为双重弹出对话框导致不好使）
const poiSearch = () => {
  // 实现输入提示
  auto.value = new AMapObj.AutoComplete(autoOptions)
  const placeSearch = new AMapObj.PlaceSearch({
    map: map,
    city: '', // 减小搜索范围至某个城市
    pageSize: 2, // 单页显示结果条数
    pageIndex: 1, // 页码
    citylimit: false, // 是否强制限制在设置的城市内搜索
    autoFitView: true,
    panel: "panel", // 结果列表将在此容器中进行展示。出不来时设置样式z-inde: 999
  })
  auto.value.on("select", function (e: any) {
    //针对选中的poi实现自己的功能
    placeSearch.search(e.poi.name);
  });
}


// 鼠标双击事件
const doubleClick = (e: any) => {
  console.log('您在 [ ' + e.lnglat.getLng() + ',' + e.lnglat.getLat() + ' ] 的位置双击了地图！')
}
// 鼠标移动事件
const showInfoMove = () => {
  console.log('您移动了您的鼠标！')
}
// 鼠标点击事件
const signClick = (e: any) => {
  console.log('您在 [ ' + e.lnglat.getLng() + ',' + e.lnglat.getLat() + ' ] 的位置单击了地图！')
  const x = e.lnglat.getLng()
  const y = e.lnglat.getLat()

  // 触发自定义事件，向父组件传递经纬度（保留6位小数）
  emit('coordinate-select', {
    longitude: x.toFixed(6),
    latitude: y.toFixed(6)
  });

  // 1. 创建/更新点标记（自动清除上一个）
  createMarker(x, y);
  // 2. 显示信息窗体
  showInfo(e, x, y);
}

// 为地图绑定点击事件
const bindEvent = () => {
  console.log("事件绑定成功")
  // map.on('dblclick', doubleClick)
  // map.on('mousemove', showInfoMove)
  map.on('click', signClick)
}

// 信息窗体
const showInfo = (e: any, x: any, y: any,) => {
  geocoder.getAddress(e.lnglat, (status, result) => {
    if (status === 'complete' && result.regeocode) {
      const address = result.regeocode.formattedAddress
      // 如果信息窗体有图片的话，需要注意下写法
      const infoContent = `
        <div style="padding:7px 0px 0px 0px;">
          <div class="global-header">当前位置</div>
          <p class='input-item'>经度: ${x}</p>
          <p class='input-item'>纬度: ${y}</p>
          <p class='input-item'>地址: ${address}</p>
        </div>
      `
      const infoWindow = new AMapObj.InfoWindow({
        content: infoContent
      })
      infoWindow.open(map, new AMapObj.LngLat(x, y))
    } else {
      console.error('获取地址失败')
    }
  })
}


// 创建点标记（接收经纬度、自动清除上一个）
const createMarker = (x: number, y: number) => {
  // 1. 清除上一个点标记（如果存在）
  if (currentMarker.value) {
    map.remove(currentMarker.value);
    currentMarker.value = null;
  }

  // 2. 点标记内容
  const markerContent = `
    <div class="custom-content-marker">
      <img src="//a.amap.com/jsapi_demos/static/demo-center/icons/poi-marker-default.png">
    </div>
  `;

  // 3. 创建新的点标记
  const position = new AMapObj.LngLat(x, y);
  const marker = new AMapObj.Marker({
    position: position,
    content: markerContent,
    offset: new AMapObj.Pixel(-13, -30),
  });

  // 4. 添加到地图并保存实例
  map.add(marker);
  currentMarker.value = marker;
};


// 覆盖物
// 绘制矩形
const drawRect = () => {
  console.log('绘制矩形')
  mouseTool.rectangle({
    strokeColor: 'red',
    strokeOpacity: 0.5,
    strokeWeight: 2,
    fillColor: 'blue',
    fillOpacity: 0.2,
    strokeStyle: 'solid',
  })
}
// 绘制圆形
const drawCircle = () => {
  console.log('绘制圆形')
  mouseTool.circle({
    strokeColor: "#FF33FF",
    strokeWeight: 6,
    strokeOpacity: 0.2,
    fillColor: '#1791fc',
    fillOpacity: 0.4,
    // strokeStyle: 'solid',
    strokeStyle: 'dashed',
    strokeDasharray: [30, 10],
  })
}
/* // 绘制多边形
const drawOther = () => {
  mouseTool.polygon({
    strokeColor: "#FF33FF",
    strokeOpacity: 1,
    strokeWeight: 4,
    strokeOpacity: 0.2,
    fillColor: '#1791fc',
    fillOpacity: 0.2,
    strokeStyle: "solid",
  })
} */
/**
 * 停止绘制
 * 形参为true时，清除所有绘制的覆盖物
 * 形参为false时，仅仅停止绘制，不会清除覆盖物
 */
const stopDrawAndClear = () => {
  mouseTool.close(true)
}


// ===================== 新增：摄像头数据相关 =====================
// 摄像头查询参数
const cameraQueryParams = reactive({
  current: 1,
  size: 200, // 加大默认条数，显示更多摄像头
})
// 摄像头列表
const cameraList = ref<Camera[]>([])
// 加载状态
const cameraLoading = ref(false)
// 存储所有摄像头标记，方便后续清理
const cameraMarkers = ref<any[]>([])

// 获取摄像头数据并在控制台输出
const getCameraData = async () => {
  cameraLoading.value = true
  try {
    // 调用和管理界面相同的接口获取数据
    const res = await getCameraList(cameraQueryParams)
    cameraList.value = res.records

    // 控制台输出数据（便于观察）
    console.log('======= 摄像头数据 =======')
    console.log('总数量：', res.total)
    console.log('当前页数据：', cameraList.value)
    console.log('=========================')

    // 清除原有摄像头标记
    clearCameraMarkers()

    // 为每个摄像头在地图上创建标记
    if (cameraList.value.length > 0) {
      cameraList.value.forEach(camera => {
        if (camera.longitude && camera.latitude) {
          createCameraMarker(camera)
          console.log(`摄像头【${camera.name}】已在地图标记，坐标：${camera.longitude.toFixed(6)}, ${camera.latitude.toFixed(6)}`)
        } else {
          console.log(`摄像头【${camera.name}】无经纬度信息，跳过标记`)
        }
      })
    } else {
      console.log('未查询到摄像头数据')
    }
  } catch (error) {
    console.error('获取摄像头数据失败：', error)
  } finally {
    cameraLoading.value = false
  }
}

// 为摄像头创建专属标记
const createCameraMarker = (camera: Camera) => {
  // 自定义摄像头标记样式（区分普通点击标记）
  const markerContent = `
    <div class="camera-marker" style="text-align:center;cursor:pointer;">
      <img src="//a.amap.com/jsapi_demos/static/demo-center/icons/poi-marker-red.png" 
           style="width:32px;height:32px;filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));">
      <div style="font-size:12px;color:#333;margin-top:4px;background:white;padding:2px 4px;border-radius:2px;white-space:nowrap;">
        ${camera.name}
      </div>
    </div>
  `;

  const position = new AMapObj.LngLat(camera.longitude, camera.latitude);
  const marker = new AMapObj.Marker({
    position: position,
    content: markerContent,
    offset: new AMapObj.Pixel(-16, -35), // 调整偏移使标记居中
    zIndex: 200, // 提高层级，避免被其他覆盖物遮挡
  });

  // 绑定点击事件，显示摄像头详情
  marker.on('click', () => {
    const statusText = camera.status === 1 ? '在线' : camera.status === 2 ? '故障' : '离线'

    const infoContent = `
      <div style="padding:10px;min-width:200px;">
        <div style="font-weight:bold;font-size:14px;margin-bottom:8px;color:#333;">${camera.name}</div>
        <div style="font-size:12px;line-height:1.6;">
          <p><span style="color:#666;">安装位置：</span>${camera.location || '未填写'}</p>
          <p><span style="color:#666;">RTSP地址: </span>${camera.rtspUrl || '未填写'}</p>
          <p><span style="color:#666;">设备状态：</span><span style="${camera.status === 1 ? 'color:green' : camera.status === 2 ? 'color:red' : 'color:orange'}">${statusText}</span></p>
          <p><span style="color:#666;">经纬度：</span>${camera.longitude.toFixed(6)}, ${camera.latitude.toFixed(6)}</p>
        </div>
      </div>
    `;

    const infoWindow = new AMapObj.InfoWindow({
      content: infoContent,
      offset: new AMapObj.Pixel(0, -40),
    });
    infoWindow.open(map, position);
  });

  // 添加到地图并保存标记实例
  map.add(marker);
  cameraMarkers.value.push(marker);
}

// 清除所有摄像头标记
const clearCameraMarkers = () => {
  if (cameraMarkers.value.length > 0) {
    map.remove(cameraMarkers.value);
    cameraMarkers.value = [];
  }
}
// ===================== 摄像头数据相关结束 =====================


// 新增：接收经纬度执行地图定位
const setCameraLocation = (lng: number, lat: number, zoom: number = 16) => {
  if (!map) {
    console.warn('地图实例未初始化');
    ElMessage.warning('地图尚未加载完成，请稍后重试');
    return;
  }
  // 执行缩放和中心定位
  map.setZoomAndCenter(zoom, [lng, lat]);
};

// 暴露方法给父组件调用
defineExpose({
  setCameraLocation,
});


onUnmounted(() => {
  map?.destroy();
});
</script>


<style lang="scss" scoped>
.map-wrapper {
  #amap {
    width: 100%;
    height: 87vh;
  }

  .draw-area {
    position: absolute;
    bottom: 10px;
    right: 200px;
    display: flex;
    justify-content: center;

    .select {
      background-color: white;
      padding: 0 10px;
      margin-right: 10px;
      border: 1px solid #ccc;
      border-radius: 5px;
    }

    .action {
      display: flex;
      align-items: center;
    }
  }

  .search-container {
    position: absolute;
    top: 65px;
    left: 300px;
    width: 300px;
    z-index: 999; // 使用变量
  }

  #panel {
    position: absolute;
    top: 180px;
    left: 200px;
    z-index: 999; // 使用变量
  }
}
</style>
