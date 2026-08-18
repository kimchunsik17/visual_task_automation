import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import UIEngine from '../components/UIEngine';

export default function CustomAppViewerPage() {
  const { appId } = useParams();
  const [appData, setAppData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [components, setComponents] = useState([]);
  const [logicGraph, setLogicGraph] = useState(null);
  const [rootStyle, setRootStyle] = useState({});
  const [globalCss, setGlobalCss] = useState('');

  useEffect(() => {
    const fetchApp = async () => {
      try {
        const res = await axios.get(`/api/apps/custom/${appId}`);
        const data = res.data;
        setAppData(data);
        
        if (data.ui_graph_data) {
          setComponents(injectWorkflows(data.ui_graph_data.components || [], data.workflow_mappings));
          setRootStyle(data.ui_graph_data.rootStyle || { backgroundColor: '#f1f5f9', padding: '2rem' });
          if (data.ui_graph_data.globalCss) {
             setGlobalCss(data.ui_graph_data.globalCss);
          }
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

  const injectWorkflows = (components, workflowMappings) => {
    return components.map(comp => {
      const newComp = { ...comp, props: { ...comp.props } };
      if (workflowMappings && workflowMappings[comp.id]) {
        const mapping = workflowMappings[comp.id];
        newComp.props.workflowId = typeof mapping === 'object' && mapping !== null ? (mapping.projectId || mapping.id) : String(mapping);
      }
      if (newComp.children) {
        newComp.children = injectWorkflows(newComp.children, workflowMappings);
      }
      return newComp;
    });
  };

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

  return (
    <>
      {globalCss && <style>{globalCss}</style>}
      <div style={{ backgroundColor: '#1e1e1e', minHeight: '100vh', padding: '2rem', display: 'flex', justifyContent: 'center' }}>
        <div style={{ 
          backgroundColor: rootStyle.backgroundColor || '#f1f5f9',
          padding: rootStyle.padding || '0px',
          position: 'relative',
          width: '100%',
          maxWidth: '800px',
          minHeight: 'calc(100vh - 4rem)',
          margin: '0 auto',
          boxSizing: 'border-box',
          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
          borderRadius: '8px',
          overflowY: 'auto'
        }}>
          <UIEngine 
            components={components} 
            logicGraph={logicGraph}
            isPreview={true} 
          />
        </div>
      </div>
    </>
  );
}
