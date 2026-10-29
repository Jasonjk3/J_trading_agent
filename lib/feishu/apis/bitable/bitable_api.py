#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书多维表格 API
提供多维表格相关的 API 接口
"""
from typing import Optional, Dict, Any, List
from loguru import logger

from lib.feishu.base.feishu_public import ValidateResponseException
from lib.feishu.base.http_client import FeishuHttpClient
from ..base import FeishuBaseApi


class FeishuBitableApi(FeishuBaseApi):
    """飞书多维表格 API 类"""

    def batch_create_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]],
        user_id_type: str = 'open_id',
        client_token: Optional[str] = None,
        ignore_consistency_check: bool = False
    ) -> Dict[str, Any]:
        """
        批量创建多维表格记录
        在多维表格数据表中新增多条记录，单次调用最多新增 1,000 条记录。
        
        Args:
            app_token: 多维表格 App 的唯一标识
            table_id: 多维表格数据表的唯一标识
            records: 要新增的记录列表，格式：[{"fields": {"字段名": "值"}}]
            user_id_type: 用户 ID 类型，可选值：open_id、union_id、user_id，默认值：open_id
            client_token: 操作的唯一标识，用于幂等的进行更新操作，格式为标准的 uuidv4
            ignore_consistency_check: 是否忽略一致性读写检查，默认为 false
            
        Returns:
            创建结果信息，包含 records 列表
        """
        url = f'{FeishuHttpClient.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {'user_id_type': user_id_type}
            if client_token:
                params['client_token'] = client_token
            if ignore_consistency_check:
                params['ignore_consistency_check'] = ignore_consistency_check

            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data={'records': records},
                params=params
            )

            return data['data']
        except ValidateResponseException as e:
            logger.error(f'批量创建多维表格记录失败: {e}')
            raise
        except Exception as e:
            logger.error(f'批量创建多维表格记录失败: {e}')
            raise ValidateResponseException(f'批量创建多维表格记录失败: {str(e)}')

    def create_record(
        self,
        app_token: str,
        table_id: str,
        fields: Dict[str, Any],
        user_id_type: str = 'open_id',
        client_token: Optional[str] = None,
        ignore_consistency_check: bool = False
    ) -> Dict[str, Any]:
        """
        创建单个多维表格记录
        在多维表格数据表中新增单条记录。
        
        Args:
            app_token: 多维表格 App 的唯一标识
            table_id: 多维表格数据表的唯一标识
            fields: 记录字段数据，格式：{"字段名": "值"}
            user_id_type: 用户 ID 类型，可选值：open_id、union_id、user_id，默认值：open_id
            client_token: 操作的唯一标识，用于幂等的进行更新操作，格式为标准的 uuidv4
            ignore_consistency_check: 是否忽略一致性读写检查，默认为 false
            
        Returns:
            创建结果信息
        """
        records = [{"fields": fields}]
        return self.batch_create_records(
            app_token=app_token,
            table_id=table_id,
            records=records,
            user_id_type=user_id_type,
            client_token=client_token,
            ignore_consistency_check=ignore_consistency_check
        )

    def batch_update_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]],
        user_id_type: str = 'open_id',
        client_token: Optional[str] = None,
        ignore_consistency_check: bool = False
    ) -> Dict[str, Any]:
        """
        批量更新多维表格记录
        在多维表格数据表中更新多条记录，单次调用最多更新 500 条记录。
        
        Args:
            app_token: 多维表格 App 的唯一标识
            table_id: 多维表格数据表的唯一标识
            records: 要更新的记录列表，格式：[{"record_id": "rec123", "fields": {"字段名": "值"}}]
            user_id_type: 用户 ID 类型，可选值：open_id、union_id、user_id，默认值：open_id
            client_token: 操作的唯一标识，用于幂等的进行更新操作，格式为标准的 uuidv4
            ignore_consistency_check: 是否忽略一致性读写检查，默认为 false
            
        Returns:
            更新结果信息
        """
        url = f'{FeishuHttpClient.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {'user_id_type': user_id_type}
            if client_token:
                params['client_token'] = client_token
            if ignore_consistency_check:
                params['ignore_consistency_check'] = ignore_consistency_check

            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data={'records': records},
                params=params
            )

            return data['data']
        except ValidateResponseException as e:
            logger.error(f'批量更新多维表格记录失败: {e}')
            raise
        except Exception as e:
            logger.error(f'批量更新多维表格记录失败: {e}')
            raise ValidateResponseException(f'批量更新多维表格记录失败: {str(e)}')

    def update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: Dict[str, Any],
        user_id_type: str = 'open_id',
        client_token: Optional[str] = None,
        ignore_consistency_check: bool = False
    ) -> Dict[str, Any]:
        """
        更新单个多维表格记录
        在多维表格数据表中更新单条记录。
        
        Args:
            app_token: 多维表格 App 的唯一标识
            table_id: 多维表格数据表的唯一标识
            record_id: 记录的唯一标识
            fields: 记录字段数据，格式：{"字段名": "值"}
            user_id_type: 用户 ID 类型，可选值：open_id、union_id、user_id，默认值：open_id
            client_token: 操作的唯一标识，用于幂等的进行更新操作，格式为标准的 uuidv4
            ignore_consistency_check: 是否忽略一致性读写检查，默认为 false
            
        Returns:
            更新结果信息
        """
        records = [{"record_id": record_id, "fields": fields}]
        return self.batch_update_records(
            app_token=app_token,
            table_id=table_id,
            records=records,
            user_id_type=user_id_type,
            client_token=client_token,
            ignore_consistency_check=ignore_consistency_check
        )

    def batch_delete_records(
        self,
        app_token: str,
        table_id: str,
        record_ids: List[str],
        user_id_type: str = 'open_id',
        client_token: Optional[str] = None,
        ignore_consistency_check: bool = False
    ) -> Dict[str, Any]:
        """
        批量删除多维表格记录
        在多维表格数据表中删除多条记录，单次调用最多删除 500 条记录。
        
        Args:
            app_token: 多维表格 App 的唯一标识
            table_id: 多维表格数据表的唯一标识
            record_ids: 要删除的记录ID列表，格式：["rec123", "rec456"]
            user_id_type: 用户 ID 类型，可选值：open_id、union_id、user_id，默认值：open_id
            client_token: 操作的唯一标识，用于幂等的进行更新操作，格式为标准的 uuidv4
            ignore_consistency_check: 是否忽略一致性读写检查，默认为 false
            
        Returns:
            删除结果信息
        """
        url = f'{FeishuHttpClient.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {'user_id_type': user_id_type}
            if client_token:
                params['client_token'] = client_token
            if ignore_consistency_check:
                params['ignore_consistency_check'] = ignore_consistency_check

            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data={'records': record_ids},
                params=params
            )

            return data['data']
        except ValidateResponseException as e:
            logger.error(f'批量删除多维表格记录失败: {e}')
            raise
        except Exception as e:
            logger.error(f'批量删除多维表格记录失败: {e}')
            raise ValidateResponseException(f'批量删除多维表格记录失败: {str(e)}')

    def delete_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        user_id_type: str = 'open_id',
        client_token: Optional[str] = None,
        ignore_consistency_check: bool = False
    ) -> Dict[str, Any]:
        """
        删除单个多维表格记录
        在多维表格数据表中删除单条记录。
        
        Args:
            app_token: 多维表格 App 的唯一标识
            table_id: 多维表格数据表的唯一标识
            record_id: 记录的唯一标识
            user_id_type: 用户 ID 类型，可选值：open_id、union_id、user_id，默认值：open_id
            client_token: 操作的唯一标识，用于幂等的进行更新操作，格式为标准的 uuidv4
            ignore_consistency_check: 是否忽略一致性读写检查，默认为 false
            
        Returns:
            删除结果信息
        """
        return self.batch_delete_records(
            app_token=app_token,
            table_id=table_id,
            record_ids=[record_id],
            user_id_type=user_id_type,
            client_token=client_token,
            ignore_consistency_check=ignore_consistency_check
        )

    def search_records(
        self,
        app_token: str,
        table_id: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
        user_id_type: str = 'open_id',
        view_id: Optional[str] = None,
        field_names: Optional[List[str]] = None,
        sort: Optional[List[Dict[str, Any]]] = None,
        filter: Optional[Dict[str, Any]] = None,
        automatic_fields: bool = False
    ) -> Dict[str, Any]:
        """
        查询多维表格记录（使用官方搜索接口 records/search）
        单次最多查询500条，支持分页、视图、字段筛选、排序与条件过滤。

        Args:
            app_token: 多维表格 App 的唯一标识
            table_id: 多维表格数据表的唯一标识
            page_size: 分页大小（1~500），默认100
            page_token: 分页标记
            user_id_type: 用户 ID 类型：open_id/union_id/user_id，默认 open_id
            view_id: 视图ID（当传入 filter 或 sort 时，view_id 会被忽略）
            field_names: 返回字段名列表，如 ["字段1","字段2"]
            sort: 排序条件数组，例如 [{"field_name":"字段","desc":true}]
            filter: 过滤条件对象，例如 {"conjunction":"and","conditions":[...]}]
            automatic_fields: 是否返回 created_time/last_modified_time/created_by/last_modified_by
            
        Returns:
            接口返回 data 对象
        """
        url = f'{FeishuHttpClient.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/search'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {
                'user_id_type': user_id_type,
                'page_size': page_size
            }
            if page_token:
                params['page_token'] = page_token

            body = {}
            if view_id:
                body['view_id'] = view_id
            if field_names:
                body['field_names'] = field_names
            if sort:
                body['sort'] = sort
            if filter:
                body['filter'] = filter
            if automatic_fields:
                body['automatic_fields'] = True

            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data=body,
                params=params
            )

            return data['data']
        except ValidateResponseException as e:
            logger.error(f'查询多维表格记录失败: {e}')
            raise
        except Exception as e:
            logger.error(f'查询多维表格记录失败: {e}')
            raise ValidateResponseException(f'查询多维表格记录失败: {str(e)}')

