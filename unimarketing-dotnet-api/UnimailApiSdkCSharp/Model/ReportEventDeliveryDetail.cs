using System;
using System.Collections.Generic;

namespace Unimarketing.UnimailApiSdk.CSharp.Model
{
    public class ReportEventDeliveryDetail
    {

        // 符合条件的总记录数
        public int Total { get; set; }

	    // 查询页码 从1开始
        public int StartIndex { get; set; }

	    // 每页多少条记录
        public int MaxResults { get; set; }

	    // 查询开始时间
        public DateTime StartTime { get; set; }

	    // 查询结束时间
        public DateTime FinishTime { get; set; }

        public IList<EventDelivery> EventDeliveries { get; set; }

        public override string ToString()
        {
            var s = "Total=" + Total + ",StartIndex=" + StartIndex + ",MaxResults=" + MaxResults
                   + ",StartTime=" + StartTime
                   + ",FinishTime=" + FinishTime;
            foreach (var o in EventDeliveries)
            {
                s += "\n[";
                s += "id=" + o.Id + ",SendTime=" + o.SendTime + ",IdLink=" + o.IdLink + ",MessageId=" + o.MessageId + ",MessageIdLink=" + o.MessageIdLink + ",ScheduleId=" + o.ScheduleId + ",ScheduleIdLink=" + o.ScheduleIdLink
                    + ",ContactId=" + o.ContactId + ",ContactIdLink=" + o.ContactIdLink + ",DeliveryStatus=" + o.DeliveryStatus + ",Dsn=" + o.Dsn + ",Email=" + o.Email + ",EnvelopeId=" + o.EnvelopeId + ",EnvelopeIdLink=" + o.EnvelopeIdLink;
                s += "]\n";
            }

            return s;
        }

    }

    public class EventDelivery
    {

        // 邮件送达信息ID
        public long Id { get; set; }

        public string IdLink { get; set; }

        // 接收邮箱地址
        public string Email { get; set; }

        public string DeliveryStatus { get; set; }

        public string Dsn { get; set; }

        // 邮件发送时间
        public DateTime SendTime { get; set; }

        // 信封ID
        public long EnvelopeId { get; set; }

        public string EnvelopeIdLink { get; set; }

        // 联系人ID
        public long ContactId { get; set; }

        public string ContactIdLink { get; set; }

        // 发送计划ID
        public long ScheduleId { get; set; }

        public string ScheduleIdLink { get; set; }

        public long MessageId { get; set; }

        public string MessageIdLink { get; set; }
    }
}
