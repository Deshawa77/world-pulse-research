import { useState, useEffect, useCallback, useRef } from "react";
import { Cpu, HardDrive, Wifi, Gpu, Download, Upload, Database } from "lucide-react";


interface SystemMetricsProps {
  className?: string;
}

interface MetricsData {
  cpu: number;
  memory: number;
  wifi: number;
  gpu: number;
}

interface DataUsage {
  download: number; // bytes per second
  upload: number; // bytes per second
  totalDownloaded: number; // total bytes
  totalUploaded: number; // total bytes
}


export default function SystemMetrics({ className = "" }: SystemMetricsProps) {
  const [metrics, setMetrics] = useState<MetricsData>({
    cpu: 0,
    memory: 0,
    wifi: 0,
    gpu: 0,
  });

  const [dataUsage, setDataUsage] = useState<DataUsage>({
    download: 0,
    upload: 0,
    totalDownloaded: 0,
    totalUploaded: 0,
  });

  const prevBytesRef = useRef<{ down: number; up: number; time: number }>({
    down: 0,
    up: 0,
    time: Date.now(),
  });

  // Format bytes to human readable (KB, MB, GB)
  const formatBytes = (bytes: number, perSecond = false): string => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const size = sizes[Math.min(i, sizes.length - 1)];
    const value = parseFloat((bytes / Math.pow(k, i)).toFixed(1));
    return `${value} ${size}${perSecond ? "/s" : ""}`;
  };

  // Simulate system metrics (in production, this would use Performance API or backend data)
  const updateMetrics = useCallback(() => {
    // Simulate realistic system metrics with some variation
    setMetrics({
      cpu: Math.min(100, Math.max(5, 25 + Math.random() * 30 + Math.sin(Date.now() / 1000) * 10)),
      memory: Math.min(100, Math.max(20, 45 + Math.random() * 20 + Math.cos(Date.now() / 1500) * 15)),
      wifi: Math.min(100, Math.max(60, 85 + Math.random() * 10 + Math.sin(Date.now() / 800) * 5)),
      gpu: Math.min(100, Math.max(10, 35 + Math.random() * 25 + Math.cos(Date.now() / 1200) * 8)),
    });

    // Simulate data usage with realistic patterns
    const now = Date.now();
    const timeDelta = (now - prevBytesRef.current.time) / 1000; // seconds
    
    // Simulate varying data rates (higher when "streaming" data)
    const baseDownloadRate = 50000 + Math.random() * 100000; // 50-150 KB/s base
    const burstMultiplier = Math.random() > 0.7 ? 3 : 1; // Occasional bursts
    const currentDownload = baseDownloadRate * burstMultiplier;
    
    const baseUploadRate = 5000 + Math.random() * 15000; // 5-20 KB/s base
    const currentUpload = baseUploadRate;

    const newTotalDown = prevBytesRef.current.down + currentDownload * timeDelta;
    const newTotalUp = prevBytesRef.current.up + currentUpload * timeDelta;

    setDataUsage({
      download: currentDownload,
      upload: currentUpload,
      totalDownloaded: newTotalDown,
      totalUploaded: newTotalUp,
    });

    prevBytesRef.current = {
      down: newTotalDown,
      up: newTotalUp,
      time: now,
    };
  }, []);

  useEffect(() => {
    // Initial update
    updateMetrics();
    
    // Update every 2 seconds
    const interval = setInterval(updateMetrics, 2000);
    return () => clearInterval(interval);
  }, [updateMetrics]);


  const getBarColor = (value: number) => {
    if (value > 80) return "#ff3366"; // Critical - Red
    if (value > 60) return "#ff9500"; // Elevated - Orange
    if (value > 40) return "#ffd600"; // Guarded - Yellow
    return "#00e0ff"; // Stable - Cyan
  };

  const getIcon = (type: string) => {
    switch (type) {
      case "cpu":
        return <Cpu size={14} />;
      case "memory":
        return <HardDrive size={14} />;
      case "wifi":
        return <Wifi size={14} />;
      case "gpu":
        return <Gpu size={14} />;
      default:
        return null;
    }
  };

  const MetricBar = ({ 
    label, 
    value, 
    type 
  }: { 
    label: string; 
    value: number; 
    type: string;
  }) => {
    const color = getBarColor(value);
    const icon = getIcon(type);

    return (
      <div className="metric-bar-container" style={{ 
        display: "flex", 
        alignItems: "center", 
        gap: "8px",
        padding: "6px 10px",
        background: "rgba(11, 18, 32, 0.6)",
        borderRadius: "8px",
        border: "1px solid rgba(0, 224, 255, 0.15)",
      }}>
        <div style={{ 
          color: color,
          display: "flex",
          alignItems: "center",
          filter: `drop-shadow(0 0 4px ${color}66)`,
        }}>
          {icon}
        </div>
        
        <div style={{ 
          fontSize: "10px", 
          fontWeight: 600,
          color: "rgba(180, 230, 255, 0.8)",
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          minWidth: "35px",
        }}>
          {label}
        </div>

        <div style={{ 
          flex: 1,
          height: "6px",
          background: "rgba(0, 0, 0, 0.3)",
          borderRadius: "3px",
          overflow: "hidden",
          position: "relative",
        }}>
          <div style={{
            width: `${value}%`,
            height: "100%",
            background: `linear-gradient(90deg, ${color}66, ${color})`,
            borderRadius: "3px",
            transition: "width 0.5s ease-out",
            boxShadow: `0 0 8px ${color}44`,
          }} />
          
          {/* Shimmer effect */}
          <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: `linear-gradient(90deg, transparent, ${color}22, transparent)`,
            animation: "metric-shimmer 2s infinite",
          }} />
        </div>

        <div style={{ 
          fontSize: "11px", 
          fontWeight: 700,
          color: color,
          minWidth: "32px",
          textAlign: "right",
          textShadow: `0 0 8px ${color}44`,
        }}>
          {value.toFixed(0)}%
        </div>
      </div>
    );
  };

  return (
    <div className={`system-metrics-panel ${className}`} style={{
      display: "flex",
      flexDirection: "column",
      gap: "6px",
      padding: "12px",
      background: "rgba(11, 18, 32, 0.4)",
      borderRadius: "12px",
      border: "1px solid rgba(0, 224, 255, 0.2)",
      backdropFilter: "blur(8px)",
    }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        marginBottom: "4px",
        paddingBottom: "8px",
        borderBottom: "1px solid rgba(0, 224, 255, 0.15)",
      }}>
        <div style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          background: "#00e0ff",
          boxShadow: "0 0 8px #00e0ff",
          animation: "pulse-dot 2s ease-in-out infinite",
        }} />
        <span style={{
          fontSize: "10px",
          fontWeight: 700,
          color: "rgba(0, 224, 255, 0.9)",
          textTransform: "uppercase",
          letterSpacing: "1.5px",
        }}>
          System Resources
        </span>
      </div>

      <MetricBar label="CPU" value={metrics.cpu} type="cpu" />
      <MetricBar label="MEM" value={metrics.memory} type="memory" />
      <MetricBar label="WIFI" value={metrics.wifi} type="wifi" />
      <MetricBar label="GPU" value={metrics.gpu} type="gpu" />

      {/* Data Usage Section */}
      <div style={{
        marginTop: "8px",
        paddingTop: "8px",
        borderTop: "1px solid rgba(0, 224, 255, 0.15)",
      }}>
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          marginBottom: "8px",
        }}>
          <Database size={12} style={{ color: "#00e0ff" }} />
          <span style={{
            fontSize: "10px",
            fontWeight: 700,
            color: "rgba(0, 224, 255, 0.9)",
            textTransform: "uppercase",
            letterSpacing: "1px",
          }}>
            Data Transfer
          </span>
        </div>

        {/* Download Speed */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 10px",
          background: "rgba(0, 224, 255, 0.08)",
          borderRadius: "8px",
          marginBottom: "6px",
          border: "1px solid rgba(0, 224, 255, 0.15)",
        }}>
          <Download size={14} style={{ color: "#00e0ff" }} />
          <div style={{ flex: 1 }}>
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "4px",
            }}>
              <span style={{
                fontSize: "10px",
                color: "rgba(180, 230, 255, 0.8)",
                textTransform: "uppercase",
              }}>
                Download
              </span>
              <span style={{
                fontSize: "11px",
                fontWeight: 700,
                color: "#00e0ff",
                textShadow: "0 0 8px rgba(0, 224, 255, 0.4)",
              }}>
                {formatBytes(dataUsage.download, true)}
              </span>
            </div>
            <div style={{
              height: "4px",
              background: "rgba(0, 0, 0, 0.3)",
              borderRadius: "2px",
              overflow: "hidden",
            }}>
              <div style={{
                width: `${Math.min(100, (dataUsage.download / 500000) * 100)}%`,
                height: "100%",
                background: "linear-gradient(90deg, rgba(0, 224, 255, 0.4), #00e0ff)",
                borderRadius: "2px",
                transition: "width 0.5s ease-out",
                boxShadow: "0 0 8px rgba(0, 224, 255, 0.3)",
              }} />
            </div>
          </div>
        </div>

        {/* Upload Speed */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 10px",
          background: "rgba(255, 0, 255, 0.08)",
          borderRadius: "8px",
          marginBottom: "6px",
          border: "1px solid rgba(255, 0, 255, 0.15)",
        }}>
          <Upload size={14} style={{ color: "#ff00ff" }} />
          <div style={{ flex: 1 }}>
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "4px",
            }}>
              <span style={{
                fontSize: "10px",
                color: "rgba(255, 200, 255, 0.8)",
                textTransform: "uppercase",
              }}>
                Upload
              </span>
              <span style={{
                fontSize: "11px",
                fontWeight: 700,
                color: "#ff00ff",
                textShadow: "0 0 8px rgba(255, 0, 255, 0.4)",
              }}>
                {formatBytes(dataUsage.upload, true)}
              </span>
            </div>
            <div style={{
              height: "4px",
              background: "rgba(0, 0, 0, 0.3)",
              borderRadius: "2px",
              overflow: "hidden",
            }}>
              <div style={{
                width: `${Math.min(100, (dataUsage.upload / 100000) * 100)}%`,
                height: "100%",
                background: "linear-gradient(90deg, rgba(255, 0, 255, 0.4), #ff00ff)",
                borderRadius: "2px",
                transition: "width 0.5s ease-out",
                boxShadow: "0 0 8px rgba(255, 0, 255, 0.3)",
              }} />
            </div>
          </div>
        </div>

        {/* Total Data Usage */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "6px 10px",
          background: "rgba(11, 18, 32, 0.6)",
          borderRadius: "8px",
          border: "1px solid rgba(0, 224, 255, 0.1)",
        }}>
          <span style={{
            fontSize: "9px",
            color: "rgba(180, 230, 255, 0.6)",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
          }}>
            Session Total
          </span>
          <div style={{
            display: "flex",
            gap: "12px",
          }}>
            <span style={{
              fontSize: "10px",
              color: "#00e0ff",
              fontWeight: 600,
            }}>
              ↓ {formatBytes(dataUsage.totalDownloaded)}
            </span>
            <span style={{
              fontSize: "10px",
              color: "#ff00ff",
              fontWeight: 600,
            }}>
              ↑ {formatBytes(dataUsage.totalUploaded)}
            </span>
          </div>
        </div>
      </div>

      <style>{`

        @keyframes metric-shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        
        @keyframes pulse-dot {
          0%, 100% { opacity: 0.5; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}
