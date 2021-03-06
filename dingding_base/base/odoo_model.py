# -*- coding: utf-8 -*-
import logging
import uuid
from psycopg2 import ProgrammingError
from odoo import models, api, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


Model = models.Model
original_setup_base = Model._setup_base


@api.model
def _setup_base(self):
    original_setup_base(self)
    setup_approval_state_fields(self)


def setup_approval_state_fields(self):
    """安装钉钉审批状态字段"""

    def add(name, field):
        if name not in self._fields:
            self._add_field(name, field)

    self._cr.execute("SELECT COUNT(*) FROM pg_class WHERE relname = 'dingding_approval_control'")
    table = self._cr.fetchall()
    if table[0][0] > 0:
        self._cr.execute(
            """SELECT im.model 
                FROM dingding_approval_control dac 
                JOIN ir_model im 
                     ON dac.oa_model_id = im.id 
                WHERE im.model = '%s'
                """ % self._name)
        res = self._cr.fetchall()
        if len(res) != 0:
            add('dd_doc_state', fields.Char(string=u'审批描述'))
            add('dd_approval_state', fields.Selection(string=u'审批状态', selection=[('draft', '草稿'), ('approval', '审批中'), ('stop', '审批结束')],
                                                      default='draft'))
            add('dd_approval_result', fields.Selection(string=u'审批结果', selection=[('load', '等待'), ('agree', '同意'), ('refuse', '拒绝'), ('redirect', '转交')],
                                                       default='load'))
            add('dd_process_instance', fields.Char(string='钉钉审批实例id'))


Model._setup_base = _setup_base

create_origin = models.BaseModel.create

write_origin = models.BaseModel.write


@api.multi
def write(self, vals):
    dingding_approval_write(self, vals)
    return write_origin(self, vals)


def dingding_approval_write(self, vals):
    """不允许单据修改"""
    res_state_obj = self.env.get('dingding.approval.control')
    if res_state_obj is None:
        return
    # 关注与取消关注处理
    if len(vals.keys()) == 1 and list(vals.keys())[0] == 'message_follower_ids':
        return
    for res in self:
        model_id = self.env['ir.model'].sudo().search([('model', '=', res._name)]).id
        flows = res_state_obj.sudo().search([('oa_model_id', '=', model_id)])
        if not flows:
            continue
        if res.dd_approval_state == 'approval':
            # 审批中
            raise ValidationError(u'注意：单据审批中，不允许进行修改。 *_*!!')
        elif res.dd_approval_state == 'stop':
            # 审批完成
            if flows[0].ftype == 'oa':
                raise ValidationError(u'注意：单据已审批完成，不允许进行修改。 *_*!!')
    return


models.BaseModel.write = write

unlink_origin = models.BaseModel.unlink


@api.multi
def unlink(self):
    dingding_approval_unlink(self)
    return unlink_origin(self)


def dingding_approval_unlink(self):
    """非草稿单据不允许删除"""
    res_state_obj = self.env.get('dingding.approval.control')
    if res_state_obj is None:
        return
    for res in self:
        model_id = self.env['ir.model'].sudo().search([('model', '=', res._name)]).id
        flows = res_state_obj.sudo().search([('oa_model_id', '=', model_id)])
        if not flows:
            continue
        if res.dd_approval_state != 'draft':
            raise ValidationError(u'注意：非草稿单据不允许删除。 *_*!!')


models.BaseModel.unlink = unlink
