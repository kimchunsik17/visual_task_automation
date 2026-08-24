import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import UIEngine from '../components/UIEngine';
import {
  DEFAULT_CANVAS,
  applyWorkflowMappings,
  normalizeCanvas,
  normalizeComponents,
  normalizeWorkflowMappings,
  resolveCanvas,
} from '../appBuilderSchema';

export default function CustomAppViewerPage() {
  const { appId } = useParams();
  const [appData, setAppData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [components, setComponents] = useState([]);
  const [logicGraph, setLogicGraph] = useState(null);
  const [rootStyle, setRootStyle] = useState({});
  const [globalCss, setGlobalCss] = useState('');
  const [globalJs, setGlobalJs] = useState('');
  const [canvas, setCanvas] = useState(DEFAULT_CANVAS);
  const [viewportWidth, setViewportWidth] = useState(DEFAULT_CANVAS.width);
  const viewportRef = useRef(null);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return undefined;

    const updateWidth = () => setViewportWidth(element.clientWidth || DEFAULT_CANVAS.width);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const fetchApp = async () => {
      try {
        const res = await axios.get(`/api/apps/custom/${appId}`);
        const data = res.data;
        setAppData(data);
        
        if (data.ui_graph_data) {
          const loadedCanvas = normalizeCanvas(data.ui_graph_data.canvas);
          const mappings = normalizeWorkflowMappings(data.workflow_mappings);
          const loadedComponents = applyWorkflowMappings(
            normalizeComponents(data.ui_graph_data.components || [], loadedCanvas),
            mappings
          );
          setComponents(loadedComponents);
          setCanvas(resolveCanvas(loadedComponents, loadedCanvas));
          setRootStyle(data.ui_graph_data.rootStyle || { backgroundColor: '#f1f5f9', padding: '2rem' });
          if (data.ui_graph_data.globalCss) {
             setGlobalCss(data.ui_graph_data.globalCss);
          }
          setGlobalJs(data.ui_graph_data.globalJs || '');
        }
        if (data.logic_graph) {
          setLogicGraph(data.logic_graph);
        }
      } catch (err) {
        console.error(err);
        setError('앱을 불러오는 데 실패했습니다. 주소를 확인해주세요.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchApp();
  }, [appId]);

  if (isLoading) {
    return <div style={{ color: '#64748b', padding: '2rem', textAlign: 'center', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>로딩 중...</div>;
  }

  if (error || !appData) {
    return (
      <div style={{ color: '#ef4444', padding: '2rem', textAlign: 'center' }}>
        <h2>오류 발생</h2>
        <p>{error}</p>
      </div>
    );
  }

  const scale = Math.min(viewportWidth / canvas.width, 1);

  return (
    <>
      {globalCss && <style>{globalCss}</style>}
      <div style={{ backgroundColor: '#1e1e1e', minHeight: '100vh', padding: 'clamp(12px, 3vw, 32px)', boxSizing: 'border-box' }}>
        <div ref={viewportRef} style={{
          width: '100%',
          margin: '0 auto',
        }}>
          <div style={{
            position: 'relative',
            width: `${canvas.width * scale}px`,
            height: `${canvas.height * scale}px`,
            margin: '0 auto',
          }}>
            <div style={{
              position: 'absolute',
              width: `${canvas.width}px`,
              height: `${canvas.height}px`,
              transform: `scale(${scale})`,
              transformOrigin: 'top left',
              backgroundColor: rootStyle.backgroundColor || '#f1f5f9',
              overflow: 'hidden',
              boxSizing: 'border-box',
              borderRadius: '8px',
              boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
            }}>
              <UIEngine
                components={components}
                logicGraph={logicGraph}
                globalJs={globalJs}
                rootStyle={rootStyle}
                canvasWidth={canvas.width}
                canvasHeight={canvas.height}
                isPreview={true}
              />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
